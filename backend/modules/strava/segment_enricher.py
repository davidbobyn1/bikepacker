"""
backend/modules/strava/segment_enricher.py

Strava Segments API integration for community-validated route enrichment.

What this does:
  - Calls the Strava /segments/explore endpoint with a bounding box derived
    from the route corridor to find popular cycling segments in the area.
  - Selects the top N segments that best match the rider's preferences
    (climbing category, activity type).
  - Returns their midpoints as via-point waypoints to inject into the Mapbox
    routing corridor, biasing the route toward roads real cyclists love.

This is the "heatmap routing" feature — we're using community segment
popularity as a proxy for road quality and desirability.

Authentication:
  - Uses the Strava /segments/explore endpoint which only requires a valid
    Bearer token (no user OAuth needed for public segment data).
  - Set STRAVA_ACCESS_TOKEN in your .env file.
  - To get a token: go to https://www.strava.com/settings/api, create an app,
    then use the OAuth flow or the Strava Swagger UI to get a token with
    read scope. For demo purposes, a personal access token works fine.

Usage:
    from backend.modules.strava.segment_enricher import enrich_corridor_with_segments

    via_points = enrich_corridor_with_segments(
        bounds=(sw_lat, sw_lon, ne_lat, ne_lon),
        activity_type="riding",
        max_segments=5,
        min_climb_category=0,
        max_climb_category=3,
    )
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

STRAVA_EXPLORE_URL = "https://www.strava.com/api/v3/segments/explore"

# How many Strava segments to inject as via-points (more = more constrained routing)
DEFAULT_MAX_SEGMENTS = 4


@dataclass
class StravaSegment:
    """A popular Strava segment within the search bounds."""
    id: int
    name: str
    climb_category: int          # 0 = NC, 1–5 = Cat 5 to HC
    avg_grade: float             # percent
    distance_m: float
    start_latlng: list[float]    # [lat, lon]
    end_latlng: list[float]      # [lat, lon]
    elev_difference: float       # metres
    starred: bool = False

    @property
    def midpoint(self) -> tuple[float, float]:
        """Return the midpoint of the segment as (lat, lon)."""
        lat = (self.start_latlng[0] + self.end_latlng[0]) / 2
        lon = (self.start_latlng[1] + self.end_latlng[1]) / 2
        return (lat, lon)

    @property
    def climb_category_label(self) -> str:
        labels = {0: "NC", 1: "Cat 5", 2: "Cat 4", 3: "Cat 3", 4: "Cat 2", 5: "Cat 1 / HC"}
        return labels.get(self.climb_category, "Unknown")


def explore_segments(
    bounds: tuple[float, float, float, float],
    activity_type: str = "riding",
    min_cat: int = 0,
    max_cat: int = 5,
    token: Optional[str] = None,
) -> list[StravaSegment]:
    """
    Call the Strava /segments/explore endpoint.

    Args:
        bounds:        (sw_lat, sw_lon, ne_lat, ne_lon) bounding box.
        activity_type: "riding" or "running".
        min_cat:       Minimum climb category (0 = flat/NC).
        max_cat:       Maximum climb category (5 = HC).
        token:         Strava Bearer token. Falls back to STRAVA_ACCESS_TOKEN env var.

    Returns:
        List of StravaSegment objects, sorted by climb_category descending
        (most interesting climbs first).
    """
    access_token = token or os.environ.get("STRAVA_ACCESS_TOKEN", "")
    if not access_token:
        logger.warning(
            "No Strava access token found. Skipping segment enrichment. "
            "Set STRAVA_ACCESS_TOKEN in your .env file."
        )
        return []

    sw_lat, sw_lon, ne_lat, ne_lon = bounds
    bounds_str = f"{sw_lat},{sw_lon},{ne_lat},{ne_lon}"

    params = {
        "bounds": bounds_str,
        "activity_type": activity_type,
        "min_cat": min_cat,
        "max_cat": max_cat,
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        resp = requests.get(STRAVA_EXPLORE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Strava API call failed: %s — skipping enrichment", exc)
        return []

    segments = []
    for s in data.get("segments", []):
        try:
            segments.append(StravaSegment(
                id=s["id"],
                name=s["name"],
                climb_category=s.get("climb_category", 0),
                avg_grade=s.get("avg_grade", 0.0),
                distance_m=s.get("distance", 0.0),
                start_latlng=s.get("start_latlng", [0, 0]),
                end_latlng=s.get("end_latlng", [0, 0]),
                elev_difference=s.get("elev_difference", 0.0),
                starred=s.get("starred", False),
            ))
        except (KeyError, TypeError) as exc:
            logger.debug("Skipping malformed segment: %s", exc)

    # Sort: starred first, then by climb category descending
    segments.sort(key=lambda s: (s.starred, s.climb_category), reverse=True)
    logger.info("Strava explore returned %d segments for bounds %s", len(segments), bounds_str)
    return segments


def enrich_corridor_with_segments(
    origin: tuple[float, float],
    destination: tuple[float, float],
    trip_spec,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
    token: Optional[str] = None,
) -> list[tuple[float, float]]:
    """
    Find popular Strava segments within the corridor bounding box and return
    their midpoints as via-point waypoints.

    The bounding box is derived from the origin and destination with a padding
    factor so segments slightly outside the direct line are included.

    Args:
        origin:       (lat, lon) of the route start.
        destination:  (lat, lon) of the route end (or same as origin for loops).
        trip_spec:    TripSpec — used to filter segments by difficulty.
        max_segments: Maximum number of via-points to inject.
        token:        Strava Bearer token.

    Returns:
        List of (lat, lon) via-point tuples to inject into the routing corridor.
    """
    # Build bounding box with 20% padding
    lats = [origin[0], destination[0]]
    lons = [origin[1], destination[1]]
    lat_pad = max(abs(max(lats) - min(lats)) * 0.2, 0.1)
    lon_pad = max(abs(max(lons) - min(lons)) * 0.2, 0.1)

    bounds = (
        min(lats) - lat_pad,
        min(lons) - lon_pad,
        max(lats) + lat_pad,
        max(lons) + lon_pad,
    )

    # Map rider fitness to acceptable climb categories
    fitness = getattr(getattr(trip_spec, "rider_profile", None), "fitness_level", "intermediate")
    cat_map = {
        "beginner":     (0, 1),
        "intermediate": (0, 3),
        "strong":       (0, 4),
        "elite":        (0, 5),
    }
    min_cat, max_cat = cat_map.get(fitness, (0, 3))

    segments = explore_segments(
        bounds=bounds,
        activity_type="riding",
        min_cat=min_cat,
        max_cat=max_cat,
        token=token,
    )

    if not segments:
        logger.info("No Strava segments found — routing without enrichment")
        return []

    # Take top N segments and return their midpoints
    selected = segments[:max_segments]
    via_points = [s.midpoint for s in selected]

    logger.info(
        "Injecting %d Strava segment via-points: %s",
        len(via_points),
        [s.name for s in selected],
    )
    return via_points


def get_segment_details_for_ui(segments: list[StravaSegment]) -> list[dict]:
    """
    Format Strava segment data for inclusion in the frontend route response.
    These appear as "Community Highlights" in the trip narrative.
    """
    return [
        {
            "id": s.id,
            "name": s.name,
            "climb_category": s.climb_category_label,
            "avg_grade_pct": round(s.avg_grade, 1),
            "distance_km": round(s.distance_m / 1000, 1),
            "elev_difference_m": round(s.elev_difference, 0),
            "strava_url": f"https://www.strava.com/segments/{s.id}",
        }
        for s in segments
    ]
