"""
POI ingest — extracts and normalises points of interest from OSM for a subregion.

POI types ingested:
  campsite, hotel, motel, hostel, grocery, convenience_store,
  water, bike_shop, train_station, ferry, pharmacy

Overnight options (tier 1/2/3) are created for campsites and lodging.
"""

import logging
from typing import Optional

import osmnx as ox
import pandas as pd
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from backend.db.models import OvernightOption, POI
from backend.modules.graph.graph_ingest import SUBREGION_BBOXES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OSM tag queries per POI type
# Each entry: (poi_type, osm_tags_dict, confidence_score)
# ---------------------------------------------------------------------------

POI_QUERIES: list[tuple[str, dict, float]] = [
    ("campsite",          {"tourism": ["camp_site", "caravan_site"]},              0.90),
    ("hotel",             {"tourism": "hotel"},                                    0.95),
    ("motel",             {"tourism": "motel"},                                    0.95),
    ("hostel",            {"tourism": ["hostel", "guest_house"]},                  0.85),
    ("grocery",           {"shop": ["supermarket", "grocery"]},                    0.95),
    ("convenience_store", {"shop": "convenience"},                                 0.90),
    ("water",             {"amenity": ["drinking_water", "water_point"]},          0.90),
    ("water",             {"natural": "spring"},                                   0.75),
    ("bike_shop",         {"shop": "bicycle"},                                     0.95),
    ("train_station",     {"railway": ["station", "halt"]},                        0.95),
    ("ferry",             {"amenity": "ferry_terminal"},                           0.95),
    ("pharmacy",          {"amenity": "pharmacy"},                                 0.95),
]

# Overnight option config per POI type
# (overnight_type, tier, legality_type)
OVERNIGHT_CONFIG: dict[str, tuple[str, int, str]] = {
    "campsite": ("campsite", 1, "permitted"),
    "hotel":    ("hotel",    1, "permitted"),
    "motel":    ("motel",    1, "permitted"),
    "hostel":   ("hostel",   1, "permitted"),
}


def _extract_centroid(row: pd.Series) -> Optional[Point]:
    """Return a Point centroid regardless of the geometry type."""
    geom = row.get("geometry")
    if geom is None:
        return None
    if geom.geom_type == "Point":
        return geom
    try:
        return geom.centroid
    except Exception:
        return None


def _fetch_pois(bbox: tuple, poi_type: str, tags: dict, confidence: float) -> list[dict]:
    """
    Query OSM for features matching tags within bbox.

    Args:
        bbox: (west, south, east, north)
        poi_type: Normalised POI type string.
        tags: OSM tag dict for the query.
        confidence: Base confidence score for this source.

    Returns:
        List of dicts with keys: type, lat, lon, name, confidence.
    """
    try:
        gdf = ox.features_from_bbox(bbox=bbox, tags=tags)
    except Exception as e:
        # No results or Overpass error — not fatal
        logger.debug("No results for %s (%s): %s", poi_type, tags, e)
        return []

    results = []
    for _, row in gdf.iterrows():
        pt = _extract_centroid(row)
        if pt is None:
            continue
        name = row.get("name") or row.get("brand") or None
        if isinstance(name, float):  # NaN
            name = None
        results.append({
            "type": poi_type,
            "lat": float(pt.y),
            "lon": float(pt.x),
            "name": str(name) if name else None,
            "confidence": confidence,
        })

    logger.info("  %s (%s): %d results", poi_type, list(tags.keys()), len(results))
    return results


def ingest_pois(subregion: str, db: Session) -> dict:
    """
    Full POI ingest for one subregion.

    Clears existing POIs for the subregion, downloads fresh from OSM,
    and stores POI + overnight_option records.

    Args:
        subregion: One of "marin", "point_reyes", "sonoma_south".
        db: SQLAlchemy session.

    Returns:
        Stats dict: {"pois": int, "overnight_options": int}
    """
    if subregion not in SUBREGION_BBOXES:
        raise ValueError(f"Unknown subregion '{subregion}'")

    bbox = SUBREGION_BBOXES[subregion]  # (west, south, east, north)
    logger.info("Clearing existing POIs for subregion '%s'...", subregion)

    # Delete overnight_options first (FK dependency)
    existing_poi_ids = [
        row.id for row in db.query(POI.id).filter(POI.subregion == subregion).all()
    ]
    if existing_poi_ids:
        db.query(OvernightOption).filter(
            OvernightOption.poi_id.in_(existing_poi_ids)
        ).delete(synchronize_session=False)
    db.query(POI).filter(POI.subregion == subregion).delete()
    db.commit()

    poi_count = 0
    overnight_count = 0

    for poi_type, tags, confidence in POI_QUERIES:
        raw = _fetch_pois(bbox, poi_type, tags, confidence)

        for item in raw:
            poi = POI(
                type=item["type"],
                geom=from_shape(Point(item["lon"], item["lat"]), srid=4326),
                name=item["name"],
                source="osm",
                confidence_score=item["confidence"],
                subregion=subregion,
            )
            db.add(poi)
            db.flush()  # get poi.id

            # Create overnight option for camping/lodging types
            if poi_type in OVERNIGHT_CONFIG:
                overnight_type, tier, legality = OVERNIGHT_CONFIG[poi_type]

                # Bump campsites to tier 2 if name is missing (less certain)
                if poi_type == "campsite" and not item["name"]:
                    tier = 2

                option = OvernightOption(
                    poi_id=poi.id,
                    overnight_type=overnight_type,
                    tier=tier,
                    legality_type=legality,
                    reservation_known=False,
                    seasonality_known=False,
                    exact_site_known=(poi_type != "campsite"),
                    confidence_score=item["confidence"],
                )
                db.add(option)
                overnight_count += 1

            poi_count += 1

        if raw:
            db.commit()

    logger.info(
        "POI ingest complete for '%s': %d POIs, %d overnight options.",
        subregion, poi_count, overnight_count,
    )
    return {"pois": poi_count, "overnight_options": overnight_count}
