"""
GET /api/pois?south=&west=&north=&east=&types=water,campsite,bike_shop

Live Overpass API query — no DB required.
Returns POIs within the supplied bounding box, tagged by type.
Tries multiple Overpass mirrors in order until one succeeds.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
MAX_PER_TYPE = 30  # cap to keep the map readable


def _poi_type(tags: dict) -> Optional[str]:
    """Derive our normalised POI type from raw OSM tags."""
    amenity = tags.get("amenity", "")
    natural = tags.get("natural", "")
    tourism = tags.get("tourism", "")
    shop = tags.get("shop", "")

    if amenity in ("drinking_water", "water_point") or natural == "spring":
        return "water"
    if tourism == "camp_site":
        return "campsite"
    if shop == "bicycle":
        return "bike_shop"
    return None


@router.get("/pois")
async def get_pois(
    south: float = Query(..., description="Bounding box south latitude"),
    west: float = Query(..., description="Bounding box west longitude"),
    north: float = Query(..., description="Bounding box north latitude"),
    east: float = Query(..., description="Bounding box east longitude"),
    types: str = Query("water,campsite,bike_shop", description="Comma-separated POI types"),
):
    """
    Return POIs of the requested types within the bounding box.
    Single Overpass request covering all requested types at once.
    Tries multiple mirrors if the primary is unavailable.
    """
    requested = {t.strip() for t in types.split(",") if t.strip()}
    bbox = f"{south},{west},{north},{east}"  # Overpass format: S,W,N,E

    # Build a single union query for all types
    parts = []
    if "water" in requested:
        parts += [
            f'node["amenity"="drinking_water"]({bbox});',
            f'node["amenity"="water_point"]({bbox});',
            f'node["natural"="spring"]({bbox});',
        ]
    if "campsite" in requested:
        parts += [
            f'node["tourism"="camp_site"]({bbox});',
            f'way["tourism"="camp_site"]({bbox});',
        ]
    if "bike_shop" in requested:
        parts += [
            f'node["shop"="bicycle"]({bbox});',
            f'way["shop"="bicycle"]({bbox});',
        ]

    if not parts:
        return {"pois": []}

    query = f"[out:json][timeout:25];\n(\n  {'  '.join(parts)}\n);\nout center;"

    # Try each mirror in order
    data = None
    for mirror in OVERPASS_MIRRORS:
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                resp = await client.post(mirror, data={"data": query})
                resp.raise_for_status()
                data = resp.json()
                logger.info("Overpass query succeeded via %s", mirror)
                break
        except Exception as exc:
            logger.warning("Overpass mirror %s failed: %s", mirror, exc)
            continue

    if data is None:
        logger.error("All Overpass mirrors failed for bbox=%s", bbox)
        return {"pois": []}

    # Parse elements, group by type, cap per type
    counts: dict[str, int] = {}
    results = []

    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        poi_type = _poi_type(tags)
        if poi_type is None or poi_type not in requested:
            continue

        # Nodes have lat/lon directly; ways/relations expose a "center" object
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue

        if counts.get(poi_type, 0) >= MAX_PER_TYPE:
            continue
        counts[poi_type] = counts.get(poi_type, 0) + 1

        results.append({
            "type": poi_type,
            "lat": float(lat),
            "lon": float(lon),
            "name": tags.get("name") or tags.get("operator") or None,
        })

    logger.info(
        "POI query bbox=[%s] → %d results (%s)",
        bbox, len(results), counts,
    )
    return {"pois": results}
