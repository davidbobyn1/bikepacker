"""
Smoke test for hard filters + soft scorer.

Usage:
    python -m backend.scripts.test_scoring
"""

import logging
import sys

from sqlalchemy.orm import Session

from backend.db.session import engine
from backend.modules.planner.relaxation import plan_with_relaxation
from backend.schemas.trip_spec import (
    LogisticsPreferences, OvernightSpec, RelaxationPolicy,
    RiderProfile, RouteShape, SurfaceTarget, TotalDistanceKm,
    TripDays, TripPreferences, TripSpec, RelaxTo,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    spec = TripSpec(
        region="north_bay",
        trip_days=TripDays(min=2, max=3, flexibility="soft"),
        total_distance_km=TotalDistanceKm(
            min=150, max=200, flexibility="soft",
            relax_to=RelaxTo(min=120, max=240),
        ),
        route_shape=RouteShape(preferred="loop"),
        surface_target=SurfaceTarget(gravel_ratio=0.5, tolerance=0.15),
        overnight=OvernightSpec(camping_required=True, hotel_allowed=False),
        rider_profile=RiderProfile(
            fitness_level="intermediate",
            technical_skill="medium",
            overnight_experience="some",
            comfort_daily_km=75.0,
            comfort_daily_climbing_m=1200.0,
            remote_tolerance="medium",
            bailout_preference="medium",
        ),
        logistics_preferences=LogisticsPreferences(water_access_required=True),
        preferences=TripPreferences(minimize_traffic=True),
        relaxation_policy=RelaxationPolicy(),
    )

    with Session(engine) as db:
        ranked, relaxations = plan_with_relaxation(spec, db)

    logger.info("=" * 60)
    if relaxations:
        logger.info("RELAXATIONS APPLIED (%d steps):", len(relaxations))
        for r in relaxations:
            logger.info("  Step %d [%s]: %s -> %s", r.step, r.dimension, r.original_value, r.relaxed_value)
    else:
        logger.info("No relaxations needed — original spec produced results")
    logger.info("TOP RANKED TRIPS (%d passed filters):", len(ranked))
    for rank, (trip, score) in enumerate(ranked, 1):
        overnights = [d.overnight.poi.name or f"poi_{d.overnight.poi_id}"
                      for d in trip.day_plans if d.overnight]
        logger.info(
            "#%d [%.3f] %d-day | %.1f km | gravel %.0f%% | overnight_quality=%.2f | "
            "surface_fit=%.2f | traffic=%.2f | %s",
            rank, score.weighted_total, trip.trip_days,
            trip.metrics.total_distance_km,
            trip.metrics.gravel_ratio * 100,
            score.overnight_quality,
            score.surface_fit,
            score.traffic_comfort,
            " -> ".join(overnights),
        )
