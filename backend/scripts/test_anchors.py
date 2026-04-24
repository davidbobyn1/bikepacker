"""
Quick smoke test for the anchor selector against live DB data.

Usage:
    python -m backend.scripts.test_anchors
"""

import logging
import sys

from sqlalchemy.orm import Session

from backend.db.models import Base
from backend.db.session import engine
from backend.modules.planner.anchor_selector import select_anchors
from backend.schemas.trip_spec import (
    LogisticsPreferences, OvernightSpec, RelaxationPolicy,
    RiderProfile, RouteShape, SurfaceTarget, TotalDistanceKm,
    TripDays, TripPreferences, TripSpec, RelaxTo,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)


def make_test_spec() -> TripSpec:
    return TripSpec(
        region="north_bay",
        trip_days=TripDays(min=2, max=3, flexibility="soft"),
        total_distance_km=TotalDistanceKm(
            min=150, max=200, flexibility="soft",
            relax_to=RelaxTo(min=120, max=240),
        ),
        route_shape=RouteShape(preferred="loop", flexibility="soft"),
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


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)

    spec = make_test_spec()
    logger.info("Testing anchor selector for: %s, %s-day, %s km",
                spec.region, f"{spec.trip_days.min}–{spec.trip_days.max}",
                f"{spec.total_distance_km.min}–{spec.total_distance_km.max}")

    with Session(engine) as db:
        result = select_anchors(spec, db)

    logger.info("Origin: %s", result.origin.name)
    logger.info("Night-1 anchors (%d):", len(result.night1))
    for opt in result.night1:
        logger.info("  [tier %d] %s — %s (conf=%.2f)",
                    opt.tier, opt.overnight_type,
                    opt.poi.name or "(unnamed)", opt.confidence_score)

    if result.night2:
        logger.info("Night-2 coverage: %d night-1 anchors have night-2 options", len(result.night2))
