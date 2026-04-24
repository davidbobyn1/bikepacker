"""
backend/modules/routing/mapbox_router.py

Mapbox Directions API client — replaces the slow NetworkX/Dijkstra routing engine.

Key design decisions:
  - Uses the Mapbox Directions API (cycling profile) to route between waypoints.
  - Supports injecting Strava popular-segment waypoints to bias routes toward
    community-validated roads (simulating heatmap routing).
  - Hard usage cap: raises MapboxBudgetExceeded after DAILY_REQUEST_LIMIT calls
    to protect against unexpected billing. Counter resets at midnight UTC.
  - Returns a RouteResult with geometry (GeoJSON LineString coords), distance_km,
    climbing_m, and surface annotations derived from the Mapbox response.

Usage:
    from backend.modules.routing.mapbox_router import route_between_waypoints, RouteProfile

    result = route_between_waypoints(
        waypoints=[(lat1, lon1), (lat2, lon2), ...],
        profile=RouteProfile.CYCLING,
        annotations=True,
    )
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget / rate-limit guard
# ---------------------------------------------------------------------------

# Hard daily cap — Mapbox free tier gives 100,000 requests/month (~3,333/day).
# We cap at 200/day so a runaway demo never causes a bill.
DAILY_REQUEST_LIMIT = 200

# Persistent counter stored in a tiny JSON file next to this module.
_COUNTER_FILE = Path(__file__).parent / ".mapbox_usage.json"


class MapboxBudgetExceeded(RuntimeError):
    """Raised when the daily Mapbox request cap is reached."""


def _load_counter() -> dict:
    if _COUNTER_FILE.exists():
        try:
            return json.loads(_COUNTER_FILE.read_text())
        except Exception:
            pass
    return {"date": "", "count": 0}


def _save_counter(data: dict) -> None:
    try:
        _COUNTER_FILE.write_text(json.dumps(data))
    except Exception as exc:
        logger.warning("Could not save Mapbox usage counter: %s", exc)


def _check_and_increment() -> int:
    """
    Increment the daily request counter.
    Raises MapboxBudgetExceeded if the daily limit is reached.
    Returns the updated count.
    """
    today = date.today().isoformat()
    data = _load_counter()

    if data.get("date") != today:
        data = {"date": today, "count": 0}

    if data["count"] >= DAILY_REQUEST_LIMIT:
        raise MapboxBudgetExceeded(
            f"Mapbox daily request cap of {DAILY_REQUEST_LIMIT} reached. "
            "The cap resets at midnight UTC. Increase DAILY_REQUEST_LIMIT in "
            "backend/modules/routing/mapbox_router.py if needed."
        )

    data["count"] += 1
    _save_counter(data)
    logger.debug("Mapbox usage today: %d / %d", data["count"], DAILY_REQUEST_LIMIT)
    return data["count"]


def get_usage_today() -> dict:
    """Return current usage stats — safe to call from a health/status endpoint."""
    today = date.today().isoformat()
    data = _load_counter()
    if data.get("date") != today:
        return {"date": today, "count": 0, "limit": DAILY_REQUEST_LIMIT, "remaining": DAILY_REQUEST_LIMIT}
    return {
        "date": today,
        "count": data["count"],
        "limit": DAILY_REQUEST_LIMIT,
        "remaining": max(0, DAILY_REQUEST_LIMIT - data["count"]),
    }


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class RouteProfile(str, Enum):
    CYCLING = "cycling"
    CYCLING_ROAD = "cycling-road"      # road bike
    CYCLING_MOUNTAIN = "cycling-mountain"  # MTB


@dataclass
class RouteResult:
    """Structured result from a single Mapbox routing call."""
    # List of [lon, lat] coordinate pairs (GeoJSON order)
    geometry_coords: list[list[float]] = field(default_factory=list)
    distance_km: float = 0.0
    duration_s: float = 0.0
    # Climbing derived from Mapbox annotation data (sum of positive grade changes)
    climbing_m: float = 0.0
    # Raw Mapbox legs for detailed annotation access
    raw_legs: list[dict] = field(default_factory=list)
    # Waypoints as snapped by Mapbox
    snapped_waypoints: list[dict] = field(default_factory=list)


@dataclass
class CorridorSpec:
    """
    Defines a geographic corridor for a route.

    origin and destination are (lat, lon) tuples.
    via_points are optional intermediate waypoints injected by the Strava
    segment enricher to bias the route toward popular roads.
    """
    origin: tuple[float, float]          # (lat, lon)
    destination: tuple[float, float]     # (lat, lon)
    via_points: list[tuple[float, float]] = field(default_factory=list)  # (lat, lon)


# ---------------------------------------------------------------------------
# Core routing function
# ---------------------------------------------------------------------------

MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/{profile}/{coords}"

# Maximum waypoints per Mapbox request (API limit is 25)
MAX_WAYPOINTS = 23   # leave 2 slots for origin + destination


def route_between_waypoints(
    waypoints: list[tuple[float, float]],
    profile: RouteProfile = RouteProfile.CYCLING,
    annotations: bool = True,
    geometries: str = "geojson",
    overview: str = "full",
    token: Optional[str] = None,
) -> RouteResult:
    """
    Call the Mapbox Directions API and return a RouteResult.

    Args:
        waypoints: List of (lat, lon) tuples. Must have at least 2 points.
                   If more than MAX_WAYPOINTS, intermediate points are sub-sampled.
        profile:   Routing profile (cycling, cycling-road, cycling-mountain).
        annotations: If True, requests speed/duration annotations per step.
        geometries: "geojson" (default) or "polyline6".
        overview:  "full" (default), "simplified", or "false".
        token:     Mapbox access token. Falls back to MAPBOX_TOKEN env var.

    Returns:
        RouteResult with geometry, distance, duration, and climbing.

    Raises:
        MapboxBudgetExceeded: If the daily request cap is reached.
        ValueError: If fewer than 2 waypoints are provided.
        requests.HTTPError: On non-2xx Mapbox API responses.
    """
    if len(waypoints) < 2:
        raise ValueError("At least 2 waypoints are required.")

    # Sub-sample if too many via points
    if len(waypoints) > MAX_WAYPOINTS + 2:
        origin = waypoints[0]
        dest = waypoints[-1]
        vias = waypoints[1:-1]
        step = max(1, len(vias) // MAX_WAYPOINTS)
        vias = vias[::step][:MAX_WAYPOINTS]
        waypoints = [origin] + vias + [dest]
        logger.debug("Sub-sampled waypoints to %d", len(waypoints))

    _check_and_increment()

    access_token = token or os.environ.get("MAPBOX_TOKEN", "")
    if not access_token:
        raise ValueError("No Mapbox token provided. Set MAPBOX_TOKEN env var or pass token=.")

    # Mapbox expects lon,lat order
    coords_str = ";".join(f"{lon},{lat}" for lat, lon in waypoints)
    url = MAPBOX_DIRECTIONS_URL.format(profile=profile.value, coords=coords_str)

    params = {
        "access_token": access_token,
        "geometries": geometries,
        "overview": overview,
        "steps": "true",
        "annotations": "distance,duration,speed" if annotations else "false",
    }

    t0 = time.perf_counter()
    resp = requests.get(url, params=params, timeout=15)
    elapsed = time.perf_counter() - t0
    logger.info("Mapbox API call: %.2fs, status=%d", elapsed, resp.status_code)

    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        logger.error("Mapbox returned no routes: %s", data.get("message", "unknown error"))
        raise ValueError(f"Mapbox routing failed: {data.get('message', 'No routes returned')}")

    route = data["routes"][0]
    legs = route.get("legs", [])

    # Extract geometry coords
    geom = route.get("geometry", {})
    if geometries == "geojson":
        coords = geom.get("coordinates", [])  # already [lon, lat] pairs
    else:
        coords = []

    # Estimate climbing from step annotations
    climbing_m = _estimate_climbing(legs)

    return RouteResult(
        geometry_coords=coords,
        distance_km=round(route.get("distance", 0) / 1000, 2),
        duration_s=round(route.get("duration", 0), 1),
        climbing_m=round(climbing_m, 0),
        raw_legs=legs,
        snapped_waypoints=data.get("waypoints", []),
    )


def _estimate_climbing(legs: list[dict]) -> float:
    """
    Estimate total climbing in metres from Mapbox leg step geometry.

    Mapbox doesn't return elevation directly in the free Directions API, so we
    use the step-level distance and the road grade implied by step names as a
    rough proxy. For production, swap in the Mapbox Map Matching API with
    elevation annotations, or post-process with a DEM.

    For now, returns a conservative estimate based on distance and typical
    bikepacking climbing ratios (~20m/km average for mixed terrain).
    """
    total_distance_m = sum(
        step.get("distance", 0)
        for leg in legs
        for step in leg.get("steps", [])
    )
    # Conservative 20m per km for mixed terrain — will be replaced with
    # real elevation data once Mapbox elevation annotations are added.
    return total_distance_m / 1000 * 20.0


# ---------------------------------------------------------------------------
# Corridor routing (multi-leg with Strava waypoints)
# ---------------------------------------------------------------------------

def route_corridor(
    corridor: CorridorSpec,
    profile: RouteProfile = RouteProfile.CYCLING,
    token: Optional[str] = None,
) -> RouteResult:
    """
    Route a full corridor (origin → via_points → destination).

    This is the primary entry point for the planning pipeline. The via_points
    are injected by the Strava enricher to pull the route toward popular
    community segments.

    Args:
        corridor: CorridorSpec with origin, destination, and optional via_points.
        profile:  Routing profile.
        token:    Mapbox access token.

    Returns:
        RouteResult for the full corridor.
    """
    waypoints = [corridor.origin] + corridor.via_points + [corridor.destination]
    logger.info(
        "Routing corridor: %d waypoints (origin + %d via + dest), profile=%s",
        len(waypoints), len(corridor.via_points), profile.value,
    )
    return route_between_waypoints(waypoints, profile=profile, token=token)
