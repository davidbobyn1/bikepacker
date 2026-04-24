"""
DEV ONLY — Drop and recreate all database tables from current ORM models.

Use this when the DB schema is stale (e.g. columns added after initial create_all).
All data will be lost. Do not run in production.

Usage:
    python -m backend.scripts.reset_db
"""

import logging
import sys

from backend.db.models import Base
from backend.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("Recreating all tables from current models...")
    Base.metadata.create_all(bind=engine)
    logger.info("Done. Re-run seed_geo and ingest_graph scripts to repopulate.")


if __name__ == "__main__":
    main()
