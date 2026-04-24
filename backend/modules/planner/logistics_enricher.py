"""
Logistics enricher — post-assembly step.

After trips are assembled, this module queries the nearest grocery and water
POIs for each overnight stop and attaches proximity metrics to TripMetrics.
These are used by score_logistics_fit() in the soft scorer.

Design: runs a single PostGIS query per overnight per POI type, capped at 50 km.
Fast enough for MVP (< 5 overnights per trip, < 5 trips per batch).
"""

import logging
from typing import Optional

from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint
from sqlalchemy import cast, select
from sqlalchemy.orm import Session
from geoalchemy2.types import Geography

from backend.db.models import POI
from backend.modules.planner.trip_assembler import AssembledTrip

logger = logging.getLogger(__name__)

MAX_SEARCH_M = 50_000   # 50 km cap — beyond this, treat as "none found"
NO_POI_KM = 50.0        # sentinel value when no POI found within cap


def _nearest_poi_km(
    lat: float,
    lon: float,
    poi_type: str,
    db: Session,
) -> float:
    """
    Return distance in km to the nearest POI of the given type.

    Args:
        lat: Latitude of query point.
        lon: Longitude of query point.
        poi_type: One of "grocery", "convenience_store", "water", "hotel", etc.
        db: SQLAlchemy session.

    Returns:
        Distance in km, or NO_POI_KM if none found within MAX_SEARCH_M.
    """
    origin = cast(ST_MakePoint(lon, lat), Geography)
    poi_geog = cast(POI.geom, Geography)

    row = db.execute(
        select(ST_Distance(poi_geog, origin).label("dist_m"))
        .where(
            POI.type == poi_type,
            ST_DWithin(poi_geog, origin, MAX_SEARCH_M),
        )
        .order_by("dist_m")
        .limit(1)
    ).first()

    if row is None or row.dist_m is None:
        return NO_POI_KM

    return round(row.dist_m / 1000.0, 2)


def enrich_trip_logistics(trip: AssembledTrip, db: Session) -> None:
    """
    Compute logistics proximity for all overnight stops in a trip and
    attach the averages to trip.metrics.

    Modifies trip.metrics.grocery_avg_km and trip.metrics.water_avg_km in place.
    Also mutates the DayPlan.overnight POI objects to carry proximity data
    so the generate endpoint can surface them in OvernightStop output.

    Args:
        trip: Assembled trip (metrics modified in place).
        db: SQLAlchemy session.
    """
    from geoalchemy2.shape import to_shape

    grocery_distances = []
    water_distances = []

    for day_plan in trip.day_plans:
        if day_plan.overnight is None:
            continue

        poi = day_plan.overnight.poi
        pt = to_shape(poi.geom)
        lat, lon = pt.y, pt.x

        grocery_km = _nearest_poi_km(lat, lon, "grocery", db)
        # Also check convenience store as fallback
        convenience_km = _nearest_poi_km(lat, lon, "convenience_store", db)
        best_grocery = min(grocery_km, convenience_km)

        water_km = _nearest_poi_km(lat, lon, "water", db)

        grocery_distances.append(best_grocery)
        water_distances.append(water_km)

        logger.info(
            "Logistics for %s: grocery=%.1f km, water=%.1f km",
            poi.name or f"poi_{poi.id}", best_grocery, water_km,
        )

    if grocery_distances:
        trip.metrics.grocery_avg_km = round(sum(grocery_distances) / len(grocery_distances), 2)
    if water_distances:
        trip.metrics.water_avg_km = round(sum(water_distances) / len(water_distances), 2)

    logger.info(
        "Logistics enrichment: grocery_avg=%.1f km, water_avg=%.1f km",
        trip.metrics.grocery_avg_km or NO_POI_KM,
        trip.metrics.water_avg_km or NO_POI_KM,
    )


def enrich_all_logistics(trips: list[AssembledTrip], db: Session) -> None:
    """
    Run logistics enrichment for a batch of assembled trips.

    Args:
        trips: List of assembled trips to enrich.
        db: SQLAlchemy session.
    """
    for trip in trips:
        if trip.is_valid:
            try:
                enrich_trip_logistics(trip, db)
            except Exception as exc:
                logger.warning("Logistics enrichment failed for trip: %s", exc)
