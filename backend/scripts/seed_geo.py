"""
Seed subregions and origin hubs into the database.

Run from bikepacking-planner/ directory:
    python -m backend.scripts.seed_geo

Safe to re-run — skips rows that already exist.
"""

import logging
import sys

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy.orm import Session

from backend.db.models import Base, OriginHub, Subregion
from backend.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subregions — bounding boxes from CLAUDE.md (S, W, N, E)
# ---------------------------------------------------------------------------

SUBREGIONS = [
    {"name": "marin",        "bbox": (37.85, -122.65, 38.10, -122.45)},
    {"name": "point_reyes",  "bbox": (37.95, -122.95, 38.20, -122.75)},
    {"name": "sonoma_south", "bbox": (38.10, -122.80, 38.50, -122.40)},
]

# ---------------------------------------------------------------------------
# Origin hubs — from CLAUDE.md
# ---------------------------------------------------------------------------

ORIGIN_HUBS = [
    {"name": "San Francisco (Ferry Building)", "lat": 37.7955, "lon": -122.3937, "subregion": "gateway"},
    {"name": "Sausalito",                      "lat": 37.8590, "lon": -122.4852, "subregion": "marin"},
    {"name": "Fairfax",                        "lat": 37.9871, "lon": -122.5888, "subregion": "marin"},
    {"name": "Point Reyes Station",            "lat": 38.0716, "lon": -122.8072, "subregion": "point_reyes"},
    {"name": "Santa Rosa",                     "lat": 38.4404, "lon": -122.7141, "subregion": "sonoma_south"},
]


def seed(db: Session) -> None:
    # Subregions
    existing_subregions = {s.name for s in db.query(Subregion).all()}
    for s in SUBREGIONS:
        if s["name"] in existing_subregions:
            logger.info("Subregion '%s' already exists, skipping.", s["name"])
            continue
        south, west, north, east = s["bbox"]
        polygon = box(west, south, east, north)  # shapely box(minx, miny, maxx, maxy)
        db.add(Subregion(name=s["name"], geom=from_shape(polygon, srid=4326)))
        logger.info("Inserted subregion '%s'.", s["name"])

    # Origin hubs
    existing_hubs = {h.name for h in db.query(OriginHub).all()}
    for h in ORIGIN_HUBS:
        if h["name"] in existing_hubs:
            logger.info("Origin hub '%s' already exists, skipping.", h["name"])
            continue
        point = Point(h["lon"], h["lat"])
        db.add(OriginHub(name=h["name"], geom=from_shape(point, srid=4326), subregion=h["subregion"]))
        logger.info("Inserted origin hub '%s'.", h["name"])

    db.commit()
    logger.info("Seeding complete.")


if __name__ == "__main__":
    logger.info("Creating tables if needed...")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        seed(db)
