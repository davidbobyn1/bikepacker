"""
Run the POI ingest pipeline for one or more subregions.

Usage (from bikepacking-planner/ directory):

    python -m backend.scripts.ingest_pois --subregion marin
    python -m backend.scripts.ingest_pois --subregion all
"""

import argparse
import logging
import sys

from backend.db.models import Base
from backend.db.session import engine
from backend.modules.graph.graph_ingest import SUBREGION_BBOXES
from backend.modules.pois.poi_ingest import ingest_pois
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest OSM POIs into PostGIS.")
    parser.add_argument(
        "--subregion",
        required=True,
        choices=list(SUBREGION_BBOXES.keys()) + ["all"],
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    subregions = list(SUBREGION_BBOXES.keys()) if args.subregion == "all" else [args.subregion]

    for subregion in subregions:
        logger.info("=" * 60)
        logger.info("Starting POI ingest for: %s", subregion)
        logger.info("=" * 60)
        with Session(engine) as db:
            stats = ingest_pois(subregion, db)
        logger.info(
            "Finished %s — POIs: %d, overnight options: %d",
            subregion, stats["pois"], stats["overnight_options"],
        )

    logger.info("All done.")


if __name__ == "__main__":
    main()
