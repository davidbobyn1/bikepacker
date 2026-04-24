"""
Overnight anchor selector — Phase 5.

Given a TripSpec and an origin hub, finds candidate overnight stops
(OvernightOptions) reachable within each day's effort range.

For a 2-day trip: returns night-1 anchors.
For a 3-day trip: returns night-1 anchors and a night-2 mapping per night-1.

All spatial queries use PostGIS ST_DWithin on geography (metres) for accuracy.
Caps: 20–40 night-1 anchors, 10–20 night-2 anchors per algorithm_spec.md.
"""

import logging
from dataclasses import dataclass, field

from geoalchemy2.functions import ST_DWithin, ST_MakePoint
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from geoalchemy2.types import Geography

from backend.db.models import OvernightOption, OriginHub, POI
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)

NIGHT1_CAP = 12  # reduced from 30 — cuts worst-case Dijkstra calls by 60%
NIGHT2_CAP = 15
WATER_PROXIMITY_M = 5000  # must have water within 5 km


@dataclass
class AnchorResult:
    """Output of the anchor selector for one trip spec."""
    origin: OriginHub
    night1: list[OvernightOption] = field(default_factory=list)
    # Maps night-1 overnight_option.poi_id → list of night-2 options
    night2: dict[int, list[OvernightOption]] = field(default_factory=dict)


def _day_range_m(spec: TripSpec, day_number: int) -> tuple[float, float]:
    """
    Compute the min/max straight-line distance buffer (metres) for one day.

    Uses rider comfort_daily_km ±25%, then constrains to the trip spec's
    total distance divided evenly across days.

    Args:
        spec: Parsed TripSpec.
        day_number: 1 for night-1 anchor, 2 for night-2 anchor.

    Returns:
        (min_m, max_m) straight-line distance from previous overnight.
    """
    comfort = spec.rider_profile.comfort_daily_km
    days_mid = (spec.trip_days.min + spec.trip_days.max) / 2

    # Rider comfort band
    rider_min = comfort * 0.60
    rider_max = comfort * 1.40

    # Marin/North Bay terrain is sinuous — straight-line ≈ 42% of road distance
    STRAIGHT_LINE_FACTOR = 0.42

    # Trip spec band split across days
    spec_min_per_day = (spec.total_distance_km.min / days_mid) * STRAIGHT_LINE_FACTOR
    spec_max_per_day = (spec.total_distance_km.max / days_mid) * STRAIGHT_LINE_FACTOR

    # Use the spec bounds as the primary constraint, with rider comfort as a soft cap
    min_km = spec_min_per_day * 0.60   # generous inward slack — campsites cluster
    max_km = min(rider_max * STRAIGHT_LINE_FACTOR, spec_max_per_day * 1.30)

    # For day 2 of a 3-day trip, tighten outer bound so night-2 isn't too far to loop back
    if day_number == 2:
        max_km *= 0.85

    return min_km * 1000, max_km * 1000


def _has_water_nearby(poi: POI, db: Session) -> bool:
    """Return True if a water POI exists within WATER_PROXIMITY_M of this POI."""
    # Use a correlated subquery to avoid passing WKB binary as a parameter
    source_geom = select(POI.geom).where(POI.id == poi.id).scalar_subquery()
    result = db.execute(
        select(func.count()).select_from(POI).where(
            POI.type == "water",
            ST_DWithin(
                cast(POI.geom, Geography),
                cast(source_geom, Geography),
                WATER_PROXIMITY_M,
            ),
        )
    ).scalar()
    return (result or 0) > 0


def _prune(
    options: list[OvernightOption],
    spec: TripSpec,
    db: Session,
    cap: int,
) -> list[OvernightOption]:
    """
    Apply pruning rules and return at most `cap` anchors.

    Pruning rules:
    - Exclude tier 3 if remote_tolerance == "low"
    - Exclude confidence < 0.5 if overnight_experience == "none"
    - Exclude if no water within WATER_PROXIMITY_M (when water_access_required)
    - Sort by confidence desc, cap count
    """
    remote = spec.rider_profile.remote_tolerance
    experience = spec.rider_profile.overnight_experience
    water_required = spec.logistics_preferences.water_access_required

    pruned = []
    for opt in options:
        if remote == "low" and opt.tier >= 3:
            continue
        if experience == "none" and opt.confidence_score < 0.5:
            continue
        if water_required and not _has_water_nearby(opt.poi, db):
            logger.debug("Pruned anchor poi_id=%d — no water nearby", opt.poi_id)
            continue
        pruned.append(opt)

    pruned.sort(key=lambda o: o.confidence_score, reverse=True)
    return pruned[:cap]


def _query_anchors(
    origin_lat: float,
    origin_lon: float,
    min_m: float,
    max_m: float,
    spec: TripSpec,
    db: Session,
) -> list[OvernightOption]:
    """
    Query OvernightOptions whose POI falls within an annular buffer
    (min_m < distance <= max_m) from a given lat/lon.

    Optionally filters by overnight type (camping_required, hotel_allowed).
    """
    origin_geog = cast(
        ST_MakePoint(origin_lon, origin_lat), Geography
    )

    # Build overnight type filter
    allowed_types = []
    if spec.overnight.camping_required:
        allowed_types += ["campsite"]
    if spec.overnight.hotel_allowed:
        allowed_types += ["hotel", "motel", "hostel"]
    if not allowed_types:
        allowed_types = ["campsite", "hotel", "motel", "hostel"]

    poi_geog = cast(POI.geom, Geography)

    rows = db.execute(
        select(OvernightOption)
        .join(POI, OvernightOption.poi_id == POI.id)
        .where(
            OvernightOption.overnight_type.in_(allowed_types),
            ST_DWithin(poi_geog, origin_geog, max_m),
            ~ST_DWithin(poi_geog, origin_geog, min_m),
        )
        .order_by(OvernightOption.confidence_score.desc())
    ).scalars().all()

    # Eagerly load poi for pruning
    for opt in rows:
        _ = opt.poi

    return list(rows)


def _find_origin_hub(spec: TripSpec, db: Session) -> OriginHub:
    """
    Select the best origin hub for a trip spec.

    Selection priority:
    1. If spec.origin_preference is set, find the hub whose name contains that
       string (case-insensitive). Allows the parser to specify "Fairfax",
       "Point Reyes Station", etc. directly.
    2. Otherwise, pick the hub that best matches spec.region using a subregion
       priority table — prefers a hub within the riding area over the gateway.

    Args:
        spec: Validated TripSpec.
        db: SQLAlchemy session.

    Returns:
        Best matching OriginHub.

    Raises:
        ValueError if no hub is found.
    """
    # 1. Honour explicit origin preference from the parser
    if spec.origin_preference:
        pref = spec.origin_preference.strip()
        hub = db.execute(
            select(OriginHub).where(
                func.lower(OriginHub.name).contains(pref.lower())
            ).order_by(OriginHub.id)
        ).scalars().first()
        if hub:
            logger.info(
                "Origin hub resolved from preference '%s' -> '%s'",
                pref, hub.name,
            )
            return hub
        logger.warning(
            "origin_preference '%s' did not match any hub — falling back to region selection",
            pref,
        )

    # 2. Region-based priority fallback
    SUBREGION_PRIORITY: dict[str, list[str]] = {
        "north_bay":   ["marin", "point_reyes", "sonoma_south", "gateway"],
        "marin":       ["marin", "gateway"],
        "point_reyes": ["point_reyes", "marin", "gateway"],
        "sonoma":      ["sonoma_south", "marin", "gateway"],
    }
    priority = SUBREGION_PRIORITY.get(spec.region, ["marin", "gateway"])

    for subregion in priority:
        hub = db.execute(
            select(OriginHub).where(OriginHub.subregion == subregion).order_by(OriginHub.id)
        ).scalars().first()
        if hub:
            return hub

    raise ValueError(f"No origin hub found for region '{spec.region}'")


def select_anchors(spec: TripSpec, db: Session) -> AnchorResult:
    """
    Select candidate overnight anchors for a trip spec.

    Args:
        spec: Validated TripSpec from the parser.
        db: SQLAlchemy session.

    Returns:
        AnchorResult with origin hub, night-1 list, and optional night-2 mapping.
    """
    origin = _find_origin_hub(spec, db)

    from geoalchemy2.shape import to_shape
    origin_pt = to_shape(origin.geom)
    origin_lat, origin_lon = origin_pt.y, origin_pt.x

    logger.info("Anchor selection from origin '%s' (%.4f, %.4f)", origin.name, origin_lat, origin_lon)

    # Night-1 anchors
    min_m, max_m = _day_range_m(spec, day_number=1)
    logger.info("Night-1 buffer: %.1f – %.1f km straight-line", min_m / 1000, max_m / 1000)

    raw_night1 = _query_anchors(origin_lat, origin_lon, min_m, max_m, spec, db)
    logger.info("Night-1 raw candidates: %d", len(raw_night1))

    night1 = _prune(raw_night1, spec, db, cap=NIGHT1_CAP)
    logger.info("Night-1 after pruning: %d (capped at %d)", len(night1), NIGHT1_CAP)

    result = AnchorResult(origin=origin, night1=night1)

    # Night-2 anchors (3-day trips only)
    if spec.trip_days.max >= 3:
        min2_m, max2_m = _day_range_m(spec, day_number=2)
        logger.info("Night-2 buffer: %.1f – %.1f km from each night-1 anchor", min2_m / 1000, max2_m / 1000)

        for n1 in night1:
            n1_pt = to_shape(n1.poi.geom)
            raw_night2 = _query_anchors(n1_pt.y, n1_pt.x, min2_m, max2_m, spec, db)
            # Exclude same anchor used for night-1
            raw_night2 = [o for o in raw_night2 if o.poi_id != n1.poi_id]
            night2 = _prune(raw_night2, spec, db, cap=NIGHT2_CAP)
            if night2:
                result.night2[n1.poi_id] = night2

        total_n2 = sum(len(v) for v in result.night2.values())
        logger.info("Night-2 anchors: %d across %d night-1 anchors", total_n2, len(result.night2))

    return result
