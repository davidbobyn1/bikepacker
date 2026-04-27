"""
GET /api/pois?south=&west=&north=&east=&types=water,campsite,bike_shop&route=lat,lon|lat,lon|...

Live Overpass API query — no DB required.
Returns POIs within the supplied bounding box that are also within
MAX_DIST_KM of the route line (if route coords are supplied).
Tries multiple Overpass mirrors in order until one succeeds.
"""

import logging
import math
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

MAX_PER_TYPE = 15   # cap per type to keep map readable
MAX_DIST_KM = 0.75  # only show POIs within 750m of the route line


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fast haversine distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _min_dist_to_route(lat: float, lon: float, route: list[tuple[float, float]]) -> float:
    """Return the minimum distance in km from (lat, lon) to any point on the route."""
    if not route:
        return 0.0
    # Sample every Nth point for performance on long routes
    step = max(1, len(route) // 200)
    return min(_haversine_km(lat, lon, rlat, rlon) for rlat, rlon in route[::step])


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
    route: Optional[str] = Query(None, description="Pipe-separated lat,lon pairs: 'lat,lon|lat,lon|...'"),
):
    """
    Return POIs near the route line (within 750m) of the requested types.
    Falls back to bounding-box-only if no route coords are supplied.
    """
    requested = {t.strip() for t in types.split(",") if t.strip()}
    bbox = f"{south},{west},{north},{east}"  # Overpass format: S,W,N,E

    # Parse route geometry if provided
    route_coords: list[tuple[float, float]] = []
    if route:
        try:
            for pair in route.split("|"):
                parts = pair.split(",")
                if len(parts) == 2:
                    route_coords.append((float(parts[0]), float(parts[1])))
        except Exception:
            route_coords = []

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

    # Parse elements, filter by proximity, cap per type
    counts: dict[str, int] = {}
    results = []

    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        poi_type = _poi_type(tags)
        if poi_type is None or poi_type not in requested:
            continue

        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue

        # Filter to POIs near the route line
        if route_coords:
            dist = _min_dist_to_route(float(lat), float(lon), route_coords)
            if dist > MAX_DIST_KM:
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
        "POI query bbox=[%s] route_pts=%d → %d results (%s)",
        bbox, len(route_coords), len(results), counts,
    )
    return {"pois": results}
