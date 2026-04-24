"""
Smoke test for the trip assembler.

Usage:
    python -m backend.scripts.test_assembly
"""

import logging
import sys

from sqlalchemy.orm import Session

from backend.db.session import engine
from backend.modules.planner.anchor_selector import select_anchors
from backend.modules.planner.trip_assembler import assemble_trips
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
        anchors = select_anchors(spec, db)
        trips = assemble_trips(spec, anchors, db)

    logger.info("=" * 60)
    logger.info("ASSEMBLED TRIPS: %d total, %d valid",
                len(trips), sum(1 for t in trips if t.is_valid))

    for i, trip in enumerate(trips):
        m = trip.metrics
        overnights = [d.overnight.poi.name or f"poi_{d.overnight.poi_id}"
                      for d in trip.day_plans if d.overnight]
        status = "OK" if trip.is_valid else f"REJECTED ({trip.rejection_reason})"
        logger.info(
            "Trip %d [%d-day] %s | %.1f km | +%.0f m | gravel %.0f%% | "
            "closure %.1f km | overnights: %s",
            i + 1, trip.trip_days, status,
            m.total_distance_km, m.total_climbing_m,
            m.gravel_ratio * 100, m.loop_closure_km,
            " → ".join(overnights),
        )
