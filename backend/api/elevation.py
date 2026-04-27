"""
backend/api/elevation.py

Proxy endpoint for OpenTopoData SRTM elevation lookups.

The public OpenTopoData API does not send CORS headers, so browser-side
fetch calls from Vercel are blocked. This endpoint proxies the request
server-side (no CORS restriction) and returns the elevation array to the
frontend.

It also computes total_climbing_m from the elevation profile so the
backend can expose accurate climbing figures.

Usage:
    POST /api/elevation
    Body: { "locations": [[lat, lon], ...] }   (up to 100 points)
    Returns: { "elevations": [float, ...], "climbing_m": float }
"""

import logging
from typing import List

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

OPENTOPODATA_URL = "https://api.opentopodata.org/v1/srtm90m"
MAX_POINTS = 100  # OpenTopoData free tier limit per request


class ElevationRequest(BaseModel):
    locations: List[List[float]]  # list of [lat, lon]


class ElevationResponse(BaseModel):
    elevations: List[float]
    climbing_m: float


@router.post("/elevation", response_model=ElevationResponse)
def get_elevation(body: ElevationRequest) -> ElevationResponse:
    """
    Proxy elevation lookup to OpenTopoData SRTM90m.

    Accepts up to 100 [lat, lon] pairs. Returns the elevation for each
    point and the total climbing (sum of positive ascent) in metres.
    """
    pts = body.locations
    if not pts:
        raise HTTPException(status_code=400, detail="No locations provided")

    # Sub-sample to ≤100 points to stay within the API limit
    if len(pts) > MAX_POINTS:
        step = len(pts) // MAX_POINTS
        pts = pts[::step][:MAX_POINTS]

    location_str = "|".join(f"{lat},{lon}" for lat, lon in pts)

    try:
        resp = requests.post(
            OPENTOPODATA_URL,
            json={"locations": location_str},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("OpenTopoData request failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Elevation service error: {exc}")

    if data.get("status") != "OK":
        raise HTTPException(
            status_code=502,
            detail=f"OpenTopoData error: {data.get('error', 'unknown')}",
        )

    elevations = [
        float(r["elevation"]) if r.get("elevation") is not None else 0.0
        for r in data["results"]
    ]

    # Calculate total climbing (sum of positive elevation deltas)
    climbing_m = sum(
        max(0.0, elevations[i] - elevations[i - 1])
        for i in range(1, len(elevations))
    )

    return ElevationResponse(elevations=elevations, climbing_m=round(climbing_m, 1))
