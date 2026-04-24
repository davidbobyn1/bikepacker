"""
Smoke test for the leg generator.

Routes from Sausalito to Back Ranch Meadows Campground using all 4 weight variants.

Usage:
    python -m backend.scripts.test_legs
"""

import logging
import sys

from sqlalchemy.orm import Session

from backend.db.session import engine
from backend.modules.planner.leg_generator import generate_legs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Sausalito origin hub
ORIGIN_LAT, ORIGIN_LON = 37.8590, -122.4852

# Back Ranch Meadows Campground (from POI ingest)
DEST_LAT, DEST_LON = 37.9871, -122.5888  # approx Fairfax/Marin area


if __name__ == "__main__":
    logger.info("Testing leg generator: Sausalito → Back Ranch Meadows area")

    with Session(engine) as db:
        variants = generate_legs(
            origin_lat=ORIGIN_LAT,
            origin_lon=ORIGIN_LON,
            dest_lat=DEST_LAT,
            dest_lon=DEST_LON,
            subregion="marin",
            technical_skill="medium",
            db=db,
        )

    valid = [v for v in variants if v.is_valid]
    rejected = [v for v in variants if not v.is_valid]

    logger.info("=" * 50)
    logger.info("Valid variants: %d", len(valid))
    for v in valid:
        m = v.metrics
        logger.info(
            "  [%s] %.1f km | +%.0f m | gravel %.0f%% | uncertain %.1f km | traffic %.2f | scenic %.2f",
            v.weight_fn, m.distance_km, m.climb_up_m,
            m.gravel_ratio * 100, m.uncertain_km,
            m.traffic_avg, m.scenic_avg,
        )

    if rejected:
        logger.info("Rejected variants: %d", len(rejected))
        for v in rejected:
            logger.info("  [%s] reason: %s", v.weight_fn, v.rejection_reason)
