"""
Trip assembler — Phase 7.

Combines leg variants into full multi-day trips with complete metrics,
loop closure quality, and stitched route geometry.

For a 2-day trip:
    leg1 (origin -> night1) + leg2 (night1 -> origin)

For a 3-day trip:
    leg1 (origin -> night1) + leg2 (night1 -> night2) + leg3 (night2 -> origin)

Output is a list of AssembledTrip objects ready for hard filtering and scoring.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from backend.db.models import OvernightOption
from backend.modules.planner.anchor_selector import AnchorResult
from backend.modules.planner.leg_generator import LegVariant, LegMetrics, generate_legs
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)

# Max total trips to assemble before capping (avoid combinatorial explosion)
MAX_ASSEMBLIES = 30

# Weight-function preferences tried per anchor combination.
# Using different preferences for each slot produces genuinely distinct routes
# rather than minor variations of the same path.
VARIANT_PREFERENCES = ["most_unpaved", "least_traffic", "lowest_climb", "shortest"]


def _pick_leg_variant(variants: list, preference: str):
    """
    Return the LegVariant whose weight_fn matches preference.
    Falls back to the first valid variant if no exact match.
    """
    valid = [v for v in variants if v.is_valid]
    if not valid:
        return None
    for v in valid:
        if v.weight_fn == preference:
            return v
    return valid[0]


@dataclass
class DayPlan:
    """One day's leg within a trip."""
    day_number: int
    leg: LegVariant
    overnight: Optional[OvernightOption]   # None for final day (return to origin)


@dataclass
class TripMetrics:
    """Aggregate metrics across all legs of a trip."""
    total_distance_km: float
    total_climbing_m: float
    total_descending_m: float
    gravel_ratio: float
    paved_ratio: float
    uncertain_km: float
    hike_a_bike_km: float
    per_day_distance_km: list[float]
    per_day_climbing_m: list[float]
    traffic_avg: float
    scenic_avg: float
    data_quality_avg: float
    loop_closure_km: float      # straight-line gap between end of last leg and origin
    duplicate_ratio: float      # fraction of edges shared between legs (overlap penalty)
    # Logistics proximity — populated by enrich_trip_logistics() after assembly
    grocery_avg_km: Optional[float] = None   # avg km to nearest grocery from each overnight
    water_avg_km: Optional[float] = None     # avg km to nearest water from each overnight


@dataclass
class AssembledTrip:
    """A fully assembled multi-day trip candidate."""
    trip_days: int
    day_plans: list[DayPlan] = field(default_factory=list)
    metrics: Optional[TripMetrics] = None
    geometry_coords: list[tuple[float, float]] = field(default_factory=list)
    rejection_reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.rejection_reason is None

    @property
    def overnight_options(self) -> list[OvernightOption]:
        return [d.overnight for d in self.day_plans if d.overnight is not None]


def _merge_coords(legs: list[LegVariant]) -> list[tuple[float, float]]:
    """Stitch leg coordinate lists into one continuous sequence."""
    coords = []
    for i, leg in enumerate(legs):
        if i == 0:
            coords.extend(leg.geometry_coords)
        else:
            # Skip first coord of subsequent legs (duplicate of previous last)
            coords.extend(leg.geometry_coords[1:])
    return coords


def _loop_closure_km(
    end_coords: tuple[float, float],
    origin_lon: float,
    origin_lat: float,
) -> float:
    """Straight-line distance in km from route end to origin."""
    import math
    lon1, lat1 = end_coords
    dlon = math.radians(origin_lon - lon1)
    dlat = math.radians(origin_lat - lat1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(origin_lat)) * math.sin(dlon / 2) ** 2
    return round(6371 * 2 * math.asin(math.sqrt(a)), 2)


def _duplicate_ratio(legs: list[LegVariant]) -> float:
    """Fraction of node pairs that appear in more than one leg (overlap penalty)."""
    if len(legs) < 2:
        return 0.0
    all_edges: list[tuple[int, int]] = []
    for leg in legs:
        for u, v in zip(leg.node_ids, leg.node_ids[1:]):
            all_edges.append((u, v))
    total = len(all_edges)
    unique = len(set(all_edges))
    return round((total - unique) / max(total, 1), 3)


def _compute_trip_metrics(
    legs: list[LegVariant],
    origin_lon: float,
    origin_lat: float,
) -> TripMetrics:
    """Aggregate per-leg metrics into trip-level metrics."""
    total_dist = sum(l.metrics.distance_km for l in legs)
    total_climb = sum(l.metrics.climb_up_m for l in legs)
    total_descend = sum(l.metrics.climb_down_m for l in legs)
    uncertain_km = sum(l.metrics.uncertain_km for l in legs)
    hab_km = sum(l.metrics.hike_a_bike_km for l in legs)

    # Weighted gravel/paved ratio across legs
    if total_dist > 0:
        gravel_ratio = sum(l.metrics.gravel_ratio * l.metrics.distance_km for l in legs) / total_dist
        paved_ratio = sum(l.metrics.paved_ratio * l.metrics.distance_km for l in legs) / total_dist
        traffic_avg = sum(l.metrics.traffic_avg * l.metrics.distance_km for l in legs) / total_dist
        scenic_avg = sum(l.metrics.scenic_avg * l.metrics.distance_km for l in legs) / total_dist
    else:
        gravel_ratio = paved_ratio = traffic_avg = scenic_avg = 0.0

    last_coord = legs[-1].geometry_coords[-1] if legs[-1].geometry_coords else (origin_lon, origin_lat)
    closure_km = _loop_closure_km(last_coord, origin_lon, origin_lat)

    return TripMetrics(
        total_distance_km=round(total_dist, 2),
        total_climbing_m=round(total_climb, 1),
        total_descending_m=round(total_descend, 1),
        gravel_ratio=round(gravel_ratio, 3),
        paved_ratio=round(paved_ratio, 3),
        uncertain_km=round(uncertain_km, 2),
        hike_a_bike_km=round(hab_km, 2),
        per_day_distance_km=[round(l.metrics.distance_km, 2) for l in legs],
        per_day_climbing_m=[round(l.metrics.climb_up_m, 1) for l in legs],
        traffic_avg=round(traffic_avg, 3),
        scenic_avg=round(scenic_avg, 3),
        data_quality_avg=0.0,  # populated by scorer
        loop_closure_km=closure_km,
        duplicate_ratio=_duplicate_ratio(legs),
    )


def assemble_trips(
    spec: TripSpec,
    anchors: AnchorResult,
    db: Session,
) -> list[AssembledTrip]:
    """
    Assemble full trip candidates from anchor results.

    For each night-1 anchor, generates leg variants for each leg segment
    and assembles them into complete trips. Caps at MAX_ASSEMBLIES.

    Args:
        spec: Validated TripSpec.
        anchors: AnchorResult from anchor_selector.
        db: SQLAlchemy session.

    Returns:
        List of AssembledTrip objects (mix of valid and rejected).
    """
    origin_pt = to_shape(anchors.origin.geom)
    origin_lon, origin_lat = origin_pt.x, origin_pt.y
    origin_subregion = anchors.origin.subregion if anchors.origin.subregion != "gateway" else "marin"
    skill = spec.rider_profile.technical_skill
    is_3day = spec.trip_days.max >= 3 and bool(anchors.night2)

    # Target daily distance for via-point lengthening — midpoint of requested range
    # divided by max trip days, rounded to a sensible value.
    target_daily_km = (
        (spec.total_distance_km.min + spec.total_distance_km.max) / 2.0
        / max(spec.trip_days.max, 1)
    )

    trips: list[AssembledTrip] = []

    def _leg_subregions(*poi_subregions: str) -> list[str]:
        """
        Return the minimal set of subregions needed to route a single leg.

        Only includes the origin subregion + each endpoint's subregion.
        Using a per-leg set (rather than all anchor subregions upfront) keeps
        the routing graph small for legs that stay within one region, while
        still enabling cross-region routing when genuinely needed.
        """
        regions = {origin_subregion}
        for s in poi_subregions:
            if s:
                regions.add(s)
        return sorted(regions)

    for n1 in anchors.night1:
        if len(trips) >= MAX_ASSEMBLIES:
            break

        n1_pt = to_shape(n1.poi.geom)
        n1_lon, n1_lat = n1_pt.x, n1_pt.y
        n1_sub = n1.poi.subregion or origin_subregion

        # Leg 1: origin -> night-1
        leg1_subs = _leg_subregions(n1_sub)
        logger.info(
            "Generating leg1: origin -> %s (subregions: %s)",
            n1.poi.name or f"poi_{n1.poi_id}", leg1_subs,
        )
        leg1_variants = generate_legs(
            origin_lat, origin_lon, n1_lat, n1_lon, leg1_subs, skill, db,
            target_daily_km=target_daily_km,
        )
        valid_leg1 = [v for v in leg1_variants if v.is_valid]

        if not valid_leg1:
            logger.warning("No valid leg1 variants for night-1 poi_id=%d, skipping", n1.poi_id)
            continue

        if is_3day and n1.poi_id in anchors.night2:
            # 3-day trips
            for n2 in anchors.night2[n1.poi_id]:
                if len(trips) >= MAX_ASSEMBLIES:
                    break

                n2_pt = to_shape(n2.poi.geom)
                n2_lon, n2_lat = n2_pt.x, n2_pt.y
                n2_sub = n2.poi.subregion or origin_subregion

                leg2_subs = _leg_subregions(n1_sub, n2_sub)
                logger.info("Generating leg2: %s -> %s (subregions: %s)",
                            n1.poi.name or f"poi_{n1.poi_id}",
                            n2.poi.name or f"poi_{n2.poi_id}", leg2_subs)
                leg2_variants = generate_legs(
                    n1_lat, n1_lon, n2_lat, n2_lon, leg2_subs, skill, db,
                    target_daily_km=target_daily_km,
                )
                valid_leg2 = [v for v in leg2_variants if v.is_valid]
                if not valid_leg2:
                    continue

                leg3_subs = _leg_subregions(n2_sub)
                logger.info("Generating leg3: %s -> origin (subregions: %s)",
                            n2.poi.name or f"poi_{n2.poi_id}", leg3_subs)
                leg3_variants = generate_legs(
                    n2_lat, n2_lon, origin_lat, origin_lon, leg3_subs, skill, db,
                    target_daily_km=target_daily_km,
                )
                valid_leg3 = [v for v in leg3_variants if v.is_valid]
                if not valid_leg3:
                    continue

                # Assemble multiple trips per anchor combo using different variant
                # preferences so the scorer sees genuinely distinct route options.
                seen_fps: set[str] = set()
                for pref_idx, pref in enumerate(VARIANT_PREFERENCES):
                    if len(trips) >= MAX_ASSEMBLIES:
                        break
                    leg1 = _pick_leg_variant(valid_leg1, pref)
                    # Offset leg2/leg3 preference for additional diversity
                    leg2 = _pick_leg_variant(valid_leg2, VARIANT_PREFERENCES[(pref_idx + 1) % len(VARIANT_PREFERENCES)])
                    leg3 = _pick_leg_variant(valid_leg3, VARIANT_PREFERENCES[(pref_idx + 2) % len(VARIANT_PREFERENCES)])
                    if not leg1 or not leg2 or not leg3:
                        continue
                    fp = f"{leg1.weight_fn}:{leg2.weight_fn}:{leg3.weight_fn}"
                    if fp in seen_fps:
                        continue
                    seen_fps.add(fp)

                    legs = [leg1, leg2, leg3]
                    metrics = _compute_trip_metrics(legs, origin_lon, origin_lat)
                    trip = AssembledTrip(
                        trip_days=3,
                        day_plans=[
                            DayPlan(day_number=1, leg=leg1, overnight=n1),
                            DayPlan(day_number=2, leg=leg2, overnight=n2),
                            DayPlan(day_number=3, leg=leg3, overnight=None),
                        ],
                        metrics=metrics,
                        geometry_coords=_merge_coords(legs),
                    )
                    if metrics.loop_closure_km > 3.0:
                        trip.rejection_reason = f"loop_closure_gap_{metrics.loop_closure_km:.1f}km"
                    trips.append(trip)
                    logger.info(
                        "3-day trip [%s]: %.1f km, +%.0f m, gravel=%.0f%%, closure=%.1f km — %s",
                        fp, metrics.total_distance_km, metrics.total_climbing_m,
                        metrics.gravel_ratio * 100, metrics.loop_closure_km,
                        "OK" if trip.is_valid else trip.rejection_reason,
                    )
        else:
            # 2-day trips: origin -> night-1 -> origin
            logger.info("Generating leg2 (return): %s -> origin (subregions: %s)",
                        n1.poi.name or f"poi_{n1.poi_id}", leg1_subs)
            leg2_variants = generate_legs(
                n1_lat, n1_lon, origin_lat, origin_lon, leg1_subs, skill, db,
                target_daily_km=target_daily_km,
            )
            valid_leg2 = [v for v in leg2_variants if v.is_valid]

            if not valid_leg2:
                logger.warning("No valid return leg for night-1 poi_id=%d, skipping", n1.poi_id)
                continue

            # Assemble multiple trips per anchor using different variant preferences
            seen_fps: set[str] = set()
            for pref_idx, pref in enumerate(VARIANT_PREFERENCES):
                if len(trips) >= MAX_ASSEMBLIES:
                    break
                leg1 = _pick_leg_variant(valid_leg1, pref)
                # Outbound and return use offset preferences for path diversity
                leg2 = _pick_leg_variant(valid_leg2, VARIANT_PREFERENCES[(pref_idx + 1) % len(VARIANT_PREFERENCES)])
                if not leg1 or not leg2:
                    continue
                fp = f"{leg1.weight_fn}:{leg2.weight_fn}"
                if fp in seen_fps:
                    continue
                seen_fps.add(fp)

                legs = [leg1, leg2]
                metrics = _compute_trip_metrics(legs, origin_lon, origin_lat)
                trip = AssembledTrip(
                    trip_days=2,
                    day_plans=[
                        DayPlan(day_number=1, leg=leg1, overnight=n1),
                        DayPlan(day_number=2, leg=leg2, overnight=None),
                    ],
                    metrics=metrics,
                    geometry_coords=_merge_coords(legs),
                )
                if metrics.loop_closure_km > 3.0:
                    trip.rejection_reason = f"loop_closure_gap_{metrics.loop_closure_km:.1f}km"
                trips.append(trip)
                logger.info(
                    "2-day trip [%s]: %.1f km, +%.0f m, gravel=%.0f%%, closure=%.1f km — %s",
                    fp, metrics.total_distance_km, metrics.total_climbing_m,
                    metrics.gravel_ratio * 100, metrics.loop_closure_km,
                    "OK" if trip.is_valid else trip.rejection_reason,
                )

    valid = [t for t in trips if t.is_valid]
    logger.info("Assembly complete: %d valid / %d total trips", len(valid), len(trips))
    return trips
