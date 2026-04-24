"""
Run the graph ingest pipeline for one or more subregions.

Usage (from bikepacking-planner/ directory):

    # Ingest Marin only (start here):
    python -m backend.scripts.ingest_graph --subregion marin

    # Ingest all supported subregions:
    python -m backend.scripts.ingest_graph --subregion all

    # With SRTM elevation raster:
    python -m backend.scripts.ingest_graph --subregion marin --raster path/to/srtm.tif

WARNING: This script downloads from the Overpass API and will take several minutes.
Run once per subregion. Safe to re-run — existing data is replaced.
"""

import argparse
import logging
import sys

from backend.db.models import Base
from backend.db.session import engine
from backend.modules.graph.graph_ingest import SUBREGION_BBOXES, ingest_subregion
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest OSM bike graph into PostGIS.")
    parser.add_argument(
        "--subregion",
        required=True,
        choices=list(SUBREGION_BBOXES.keys()) + ["all"],
        help="Subregion to ingest, or 'all' for all subregions.",
    )
    parser.add_argument(
        "--raster",
        default=None,
        help="Optional path to SRTM .tif raster for elevation data.",
    )
    args = parser.parse_args()

    logger.info("Ensuring DB tables exist...")
    Base.metadata.create_all(bind=engine)

    subregions = list(SUBREGION_BBOXES.keys()) if args.subregion == "all" else [args.subregion]

    for subregion in subregions:
        logger.info("=" * 60)
        logger.info("Starting ingest for subregion: %s", subregion)
        logger.info("=" * 60)
        with Session(engine) as db:
            stats = ingest_subregion(subregion, db, raster_path=args.raster)
        logger.info(
            "Finished %s — nodes: %d, edges: %d, skipped: %d",
            subregion, stats["nodes"], stats["edges"], stats["skipped_edges"],
        )

    logger.info("All done.")


if __name__ == "__main__":
    main()
