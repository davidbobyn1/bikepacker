"""
backend/modules/planner/corridor_planner.py

Corridor-first planning engine — replaces the campsite-first model.

The old model routed TO campsites first, which produced short, uninspiring legs
that required hacky via-point insertion to pad them out.

This new model:
  1. Designs a geographic corridor first (a scenic arc from origin back to origin)
  2. Injects Strava popular-segment waypoints to bias the route toward great roads
  3. Routes the full corridor via Mapbox (fast, reliable, any geography)
  4. Segments the resulting route into daily legs based on rider comfort
  5. Finds overnight stops near the natural day-end points along the route
  6. Returns 3 differentiated route archetypes (scenic, easier, adventurous)

This produces routes that feel like a human guide designed them, not a
shortest-path algorithm.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from backend.modules.routing.mapbox_router import (
    RouteProfile, RouteResult, CorridorSpec, route_corridor, MapboxBudgetExceeded
)
from backend.modules.strava.segment_enricher import enrich_corridor_with_segments
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DaySegment:
    """One day's worth of riding within the full route."""
    day_number: int
    start_coord: tuple[float, float]   # (lat, lon)
    end_coord: tuple[float, float]     # (lat, lon)
    geometry_coords: list[list[float]] = field(default_factory=list)  # [lon, lat] GeoJSON
    distance_km: float = 0.0
    climbing_m: float = 0.0
    gravel_ratio: float = 0.5
    estimated_hours: float = 0.0
    overnight_name: Optional[str] = None
    overnight_coord: Optional[tuple[float, float]] = None
    overnight_type: Optional[str] = None   # campsite / hotel / dispersed


@dataclass
class PlannedRoute:
    """A fully planned route with day segments and metadata."""
    archetype: str                          # scenic / easier / adventurous
    archetype_label: str
    archetype_tagline: str
    total_distance_km: float
    total_climbing_m: float
    gravel_ratio: float
    trip_days: int
    day_segments: list[DaySegment] = field(default_factory=list)
    full_geometry_coords: list[list[float]] = field(default_factory=list)  # [lon, lat]
    strava_highlights: list[dict] = field(default_factory=list)
    mapbox_profile: str = "cycling"
    confidence_level: str = "medium"
    confidence_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Corridor design
# ---------------------------------------------------------------------------

# Archetype definitions: each modifies the corridor shape and routing profile
ARCHETYPES = {
    "scenic": {
        "label": "The Scenic Route",
        "tagline": "Maximum views, memorable terrain",
        "profile": RouteProfile.CYCLING,
        # Bias the corridor toward the coast / higher ground by deflecting
        # the midpoint in the "scenic" direction (west/uphill for North Bay)
        "corridor_deflection": "west",
        "max_strava_segments": 5,
        "strava_min_cat": 1,   # prefer segments with some climbing
    },
    "easier": {
        "label": "The Easier Way",
        "tagline": "Lower stress, better logistics",
        "profile": RouteProfile.CYCLING,
        "corridor_deflection": "east",
        "max_strava_segments": 2,
        "strava_min_cat": 0,
    },
    "adventurous": {
        "label": "The Adventure",
        "tagline": "Technical, remote, rewarding",
        # Use standard cycling profile — cycling-mountain is unavailable in many regions
        # and causes silent failures. The adventurous character comes from the corridor
        # deflection (south) and wider radius, not the Mapbox profile.
        "profile": RouteProfile.CYCLING,
        "corridor_deflection": "south",
        "max_strava_segments": 4,
        "strava_min_cat": 2,   # prefer harder segments
    },
}


def _deflect_midpoint(
    origin: tuple[float, float],
    direction: str,
    deflection_deg: float = 0.15,
) -> tuple[float, float]:
    """
    Deflect the loop midpoint in a given compass direction to create
    differentiated corridor shapes for each archetype.

    Args:
        origin:         (lat, lon) of the route origin.
        direction:      "north", "south", "east", "west".
        deflection_deg: Degrees of lat/lon to deflect.

    Returns:
        (lat, lon) of the deflected midpoint.
    """
    lat, lon = origin
    offsets = {
        "north": (deflection_deg, 0),
        "south": (-deflection_deg, 0),
        "east":  (0, deflection_deg),
        "west":  (0, -deflection_deg),
    }
    dlat, dlon = offsets.get(direction, (0, deflection_deg))
    return (lat + dlat, lon + dlon)


def _design_loop_corridor(
    origin: tuple[float, float],
    target_distance_km: float,
    archetype_config: dict,
) -> CorridorSpec:
    """
    Design a loop corridor for a given origin and target distance.

    Places 8 waypoints evenly around a circle (clockwise from a start angle
    biased by the archetype direction).  A true circular spread forces Mapbox
    to route all the way around the loop instead of cutting back across it,
    eliminating the out-and-back spaghetti shape.

    Args:
        origin:            (lat, lon) of the start/end point.
        target_distance_km: Desired total loop distance.
        archetype_config:  Archetype dict from ARCHETYPES.

    Returns:
        CorridorSpec with origin, destination (= origin for loops), and
        via_points defining the corridor shape.
    """
    # road_factor=2.0: real road distance is roughly 2x the straight-line
    # circumference for mountain/rural cycling corridors.
    # loop circumference = 2π * radius  ⇒  radius = target / (2π * road_factor)
    road_factor = 2.0
    radius_km = target_distance_km / (2 * math.pi * road_factor)
    # Convert km to approximate degrees (1 deg lat ≈ 111 km, 1 deg lon ≈ 111*cos(lat) km)
    lat, lon = origin
    radius_lat = radius_km / 111.0
    radius_lon = radius_km / (111.0 * math.cos(math.radians(lat)))

    direction = archetype_config.get("corridor_deflection", "north")

    # Start angle (degrees from north, clockwise) biased by archetype direction
    # so each archetype explores a different part of the landscape.
    start_angle_deg = {"north": 0, "south": 180, "east": 90, "west": 270}.get(direction, 0)

    # Place 8 waypoints evenly around the circle, starting from start_angle.
    # Using 8 points (every 45°) gives Mapbox enough guidance to route a full
    # loop without shortcuts while staying within the 25-waypoint API limit.
    n_points = 8
    via_points = []
    for i in range(n_points):
        angle_deg = start_angle_deg + (360.0 / n_points) * i
        angle_rad = math.radians(angle_deg)
        # North = 0°: dlat = cos(angle), dlon = sin(angle)
        dlat = math.cos(angle_rad) * radius_lat
        dlon = math.sin(angle_rad) * radius_lon
        via_points.append((lat + dlat, lon + dlon))

    return CorridorSpec(
        origin=origin,
        destination=origin,  # loop returns to start
        via_points=via_points,
    )


# ---------------------------------------------------------------------------
# Day segmentation
# ---------------------------------------------------------------------------

def _segment_route_by_days(
    result: RouteResult,
    trip_days: int,
    daily_km: float,
) -> list[DaySegment]:
    """
    Split the full route geometry into daily segments.

    Divides the route's coordinate list into trip_days roughly equal segments
    by distance, targeting daily_km per day.

    Args:
        result:     RouteResult from Mapbox.
        trip_days:  Number of days.
        daily_km:   Target km per day (used to validate, not enforce).

    Returns:
        List of DaySegment objects.
    """
    coords = result.geometry_coords
    if not coords:
        return []

    total_points = len(coords)
    points_per_day = max(1, total_points // trip_days)
    km_per_day = result.distance_km / trip_days
    climb_per_day = result.climbing_m / trip_days

    segments = []
    for day in range(trip_days):
        start_idx = day * points_per_day
        end_idx = total_points if day == trip_days - 1 else (day + 1) * points_per_day

        day_coords = coords[start_idx:end_idx]
        if not day_coords:
            continue

        start_coord = (day_coords[0][1], day_coords[0][0])   # (lat, lon) from [lon, lat]
        end_coord = (day_coords[-1][1], day_coords[-1][0])

        segments.append(DaySegment(
            day_number=day + 1,
            start_coord=start_coord,
            end_coord=end_coord,
            geometry_coords=day_coords,
            distance_km=round(km_per_day, 1),
            climbing_m=round(climb_per_day, 0),
            gravel_ratio=0.5,   # TODO: derive from Mapbox surface annotations
            estimated_hours=round(km_per_day / 15.0, 1),  # ~15 km/h bikepacking pace
        ))

    return segments


# ---------------------------------------------------------------------------
# Main planning function
# ---------------------------------------------------------------------------

def plan_routes(
    spec: TripSpec,
    mapbox_token: Optional[str] = None,
    strava_token: Optional[str] = None,
    db=None,
) -> list[PlannedRoute]:
    """
    Plan 3 differentiated route options for a given TripSpec.

    This is the new corridor-first planning engine. It:
      1. Resolves the origin coordinates from the spec
      2. For each archetype, designs a corridor and enriches it with Strava segments
      3. Routes the corridor via Mapbox
      4. Segments the route into daily legs
      5. Returns 3 PlannedRoute objects

    Args:
        spec:          Validated TripSpec from the intent parser.
        mapbox_token:  Mapbox access token (falls back to env var).
        strava_token:  Strava access token (falls back to env var).
        db:            SQLAlchemy session (used for POI lookups).

    Returns:
        List of up to 3 PlannedRoute objects. May be fewer if routing fails.
    """
    import os
    from backend.config import settings as _settings
    mapbox_token = mapbox_token or _settings.mapbox_token or os.environ.get("MAPBOX_TOKEN", "")
    strava_token = strava_token or _settings.strava_access_token or os.environ.get("STRAVA_ACCESS_TOKEN", "")

    # Resolve origin coordinates
    origin = _resolve_origin(spec, mapbox_token=mapbox_token)
    target_km = (spec.total_distance_km.min + spec.total_distance_km.max) / 2
    trip_days = spec.trip_days.min
    daily_km = spec.rider_profile.comfort_daily_km

    # Guard: target_km must be at least trip_days x daily_km.
    # If the LLM under-parsed the distance (e.g. user said "3 days" without specifying km),
    # the spec may have a small total_distance_km. Fall back to days x daily_km so the
    # corridor is sized correctly for the number of days requested.
    min_target = trip_days * daily_km
    if target_km < min_target:
        logger.warning(
            "target_km=%.0f < trip_days(%d) x daily_km(%.0f)=%.0f -- using %.0f km",
            target_km, trip_days, daily_km, min_target, min_target,
        )
        target_km = min_target

    logger.info(
        "Planning routes: origin=%s, target=%.0f km, %d days, %.0f km/day",
        origin, target_km, trip_days, daily_km,
    )

    planned_routes = []

    for archetype_key, archetype_config in ARCHETYPES.items():
        logger.info("Planning archetype: %s", archetype_key)
        try:
            route = _plan_single_archetype(
                archetype_key=archetype_key,
                archetype_config=archetype_config,
                origin=origin,
                target_km=target_km,
                trip_days=trip_days,
                daily_km=daily_km,
                spec=spec,
                mapbox_token=mapbox_token,
                strava_token=strava_token,
                db=db,
            )
            if route:
                planned_routes.append(route)
        except MapboxBudgetExceeded as exc:
            logger.error("Mapbox budget exceeded: %s", exc)
            # Add a note but don't crash — return what we have
            break
        except Exception as exc:
            logger.warning("Failed to plan archetype %s: %s", archetype_key, exc, exc_info=True)

    logger.info("Planning complete: %d routes generated", len(planned_routes))
    return planned_routes


def _plan_single_archetype(
    archetype_key: str,
    archetype_config: dict,
    origin: tuple[float, float],
    target_km: float,
    trip_days: int,
    daily_km: float,
    spec: TripSpec,
    mapbox_token: str,
    strava_token: str,
    db,
) -> Optional[PlannedRoute]:
    """Plan a single archetype route. Returns None on failure."""

    # Step 1: Design the corridor shape
    corridor = _design_loop_corridor(origin, target_km, archetype_config)

    # Step 2: Enrich with Strava popular segments
    strava_via_points = enrich_corridor_with_segments(
        origin=origin,
        destination=origin,
        trip_spec=spec,
        max_segments=archetype_config.get("max_strava_segments", 4),
        token=strava_token,
    )

    # Inject Strava waypoints into the corridor
    if strava_via_points:
        # Interleave Strava waypoints with the corridor's geographic waypoints
        corridor.via_points = _interleave_waypoints(
            corridor.via_points, strava_via_points
        )

    # Step 3: Route via Mapbox
    result = route_corridor(
        corridor=corridor,
        profile=archetype_config["profile"],
        token=mapbox_token,
    )

    if not result.geometry_coords:
        logger.warning("Mapbox returned empty geometry for archetype %s", archetype_key)
        return None

    # Step 4: Segment into daily legs
    day_segments = _segment_route_by_days(result, trip_days, daily_km)

    # Step 5: Find overnight stops near day-end points
    if db is not None:
        day_segments = _attach_overnight_stops(day_segments, spec, db)

    return PlannedRoute(
        archetype=archetype_key,
        archetype_label=archetype_config["label"],
        archetype_tagline=archetype_config["tagline"],
        total_distance_km=result.distance_km,
        total_climbing_m=result.climbing_m,
        gravel_ratio=0.5,   # TODO: derive from Mapbox surface annotations
        trip_days=trip_days,
        day_segments=day_segments,
        full_geometry_coords=result.geometry_coords,
        mapbox_profile=archetype_config["profile"].value,
        confidence_level="medium",
        confidence_notes=["Route geometry from Mapbox Directions API"],
    )


def _interleave_waypoints(
    corridor_points: list[tuple[float, float]],
    strava_points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """
    Interleave Strava waypoints with corridor waypoints.
    Strava points are inserted at positions that roughly match their
    geographic position along the corridor.
    """
    if not strava_points:
        return corridor_points
    if not corridor_points:
        return strava_points

    # Simple strategy: insert Strava points after the first corridor point
    # A more sophisticated implementation would sort by proximity to the corridor
    combined = corridor_points[:1] + strava_points[:3] + corridor_points[1:]
    return combined


def _resolve_origin(spec: TripSpec, mapbox_token: str = "") -> tuple[float, float]:
    """
    Resolve the origin coordinates from the TripSpec.
    Uses Mapbox Geocoding API to resolve any location worldwide.
    Falls back to Fairfax, CA if geocoding fails.
    """
    import requests as _requests
    from urllib.parse import quote as _quote

    # Build a query from origin_preference or region
    query = (spec.origin_preference or "").strip()
    if not query:
        query = spec.region.replace("_", " ") if spec.region and spec.region != "unknown" else ""
    if not query:
        logger.warning("No origin or region specified — defaulting to Fairfax, CA")
        return (37.9874, -122.5894)

    token = mapbox_token
    if not token:
        from backend.config import settings as _s
        token = _s.mapbox_token or ""

    try:
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{_quote(query)}.json"
        resp = _requests.get(
            url,
            params={"access_token": token, "limit": 1, "types": "place,locality,region,address"},
            timeout=10,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            lon, lat = features[0]["center"]
            logger.info("Geocoded '%s' → (%.4f, %.4f)", query, lat, lon)
            return (lat, lon)
        logger.warning("Geocoding returned no results for '%s' — defaulting to Fairfax, CA", query)
    except Exception as exc:
        logger.warning("Geocoding failed for '%s': %s — defaulting to Fairfax, CA", query, exc)

    return (37.9874, -122.5894)


def _attach_overnight_stops(
    day_segments: list[DaySegment],
    spec: TripSpec,
    db,
) -> list[DaySegment]:
    """
    Find overnight stops near the end of each day segment using the POI database.
    Skips the last day (return to origin).
    """
    try:
        from sqlalchemy import text
        for seg in day_segments[:-1]:  # skip last day
            lat, lon = seg.end_coord
            # Find the nearest campsite or hotel within 10 km
            query = text("""
                SELECT p.name, p.metadata_json, o.overnight_type, o.tier,
                       ST_Y(p.geom::geometry) as lat, ST_X(p.geom::geometry) as lon
                FROM poi p
                JOIN overnight_options o ON o.poi_id = p.id
                WHERE ST_DWithin(
                    p.geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    10000
                )
                AND (o.overnight_type IN ('campsite', 'dispersed') OR
                     (:hotel_ok AND o.overnight_type IN ('hotel', 'motel')))
                ORDER BY o.tier ASC, ST_Distance(p.geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
                LIMIT 1
            """)
            row = db.execute(query, {
                "lat": lat, "lon": lon,
                "hotel_ok": spec.overnight.hotel_allowed,
            }).fetchone()

            if row:
                seg.overnight_name = row.name or f"Overnight stop (Night {seg.day_number})"
                seg.overnight_coord = (row.lat, row.lon)
                seg.overnight_type = row.overnight_type
                logger.debug(
                    "Day %d overnight: %s (%s)",
                    seg.day_number, seg.overnight_name, seg.overnight_type,
                )
            else:
                seg.overnight_name = f"Dispersed camping area (Night {seg.day_number})"
                seg.overnight_coord = seg.end_coord  # always pin to day end point
                seg.overnight_type = "dispersed"
    except Exception as exc:
        logger.warning("Overnight stop lookup failed: %s — using end_coord fallback", exc)

    # Safety pass: ensure every intermediate day has a coord so map markers always render
    for seg in day_segments[:-1]:
        if not seg.overnight_coord:
            seg.overnight_name = seg.overnight_name or f"Night {seg.day_number} camp"
            seg.overnight_coord = seg.end_coord
            seg.overnight_type = seg.overnight_type or "dispersed"

    return day_segments
