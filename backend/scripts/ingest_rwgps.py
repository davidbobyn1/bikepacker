"""
Apply RideWithGPS community route traces as confidence boosters on graph edges.

Usage (from bikepacking-planner/ directory):

    python -m backend.scripts.ingest_rwgps --subregion marin --gpx-dir data/rwgps/marin/
    python -m backend.scripts.ingest_rwgps --subregion point_reyes --gpx-dir data/rwgps/point_reyes/
    python -m backend.scripts.ingest_rwgps --subregion marin --gpx-dir data/rwgps/marin/ --reset

How to get GPX files from RideWithGPS:
  1. Search for public routes in the target area on ridewithgps.com
  2. Open each route, click Export > GPX Track
  3. Save to data/rwgps/<subregion>/route_name.gpx
  4. Run this script

This is optional — the planner works without it. RWGPS boosts surface
confidence on well-traveled edges but never changes bike_access or route legality.
"""

import argparse
import logging
import sys

from backend.db.models import Base
from backend.db.session import engine
from backend.modules.graph.rwgps_ingest import ingest_rwgps_directory
from backend.modules.graph.graph_ingest import SUBREGION_BBOXES
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest RWGPS GPX traces as graph edge confidence boosters."
    )
    parser.add_argument(
        "--subregion",
        required=True,
        choices=list(SUBREGION_BBOXES.keys()),
        help="Subregion to apply boosts to.",
    )
    parser.add_argument(
        "--gpx-dir",
        required=True,
        help="Directory containing .gpx files to process.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Clear existing RWGPS boosts for this subregion before processing.",
    )
    args = parser.parse_args()

    with Session(engine) as db:
        stats = ingest_rwgps_directory(
            subregion=args.subregion,
            gpx_dir=args.gpx_dir,
            db=db,
            reset=args.reset,
        )

    logger.info(
        "Done: %d files, %d track points, %d edges boosted",
        stats["files"], stats["total_points"], stats["edges_boosted"],
    )


if __name__ == "__main__":
    main()
