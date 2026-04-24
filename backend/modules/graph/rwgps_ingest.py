"""
RideWithGPS confidence booster — optional, modular, non-blocking.

This module ingests public GPX traces (exported from RideWithGPS or any other
source) and uses them as an auxiliary confidence signal on graph edges. It does
NOT create new routing edges or override access/legality rules.

What it does:
  - Reads a directory of .gpx files
  - Snaps each track point to the nearest graph edge in PostGIS
  - Increments rwgps_confidence_boost on matched edges
  - Higher boost = this edge appears in many community routes = more reliable

How to get RWGPS traces for a subregion:
  1. Go to ridewithgps.com, search for routes in Marin/Point Reyes/Sonoma
  2. Export public routes as GPX (File > Export > GPX Track)
  3. Put all .gpx files in a directory (e.g., data/rwgps/marin/)
  4. Run: python -m backend.scripts.ingest_rwgps --subregion marin --gpx-dir data/rwgps/marin/

Design constraints:
  - This is strictly advisory. It adjusts surface_confidence, never bike_access.
  - An edge that was inaccessible before remains inaccessible after.
  - Boost is additive and capped at 1.0.
  - Safe to re-run (cumulative — each run adds to existing boosts).
    Use --reset to clear before re-running from scratch.
"""

import logging
from pathlib import Path
from typing import Optional

import gpxpy
import gpxpy.gpx
from geoalchemy2.functions import ST_DWithin, ST_ClosestPoint, ST_MakePoint
from shapely.geometry import Point
from sqlalchemy import cast, func, select, update
from sqlalchemy.orm import Session
from geoalchemy2.types import Geography

from backend.db.models import Edge
from backend.modules.graph.graph_ingest import SUBREGION_BBOXES

logger = logging.getLogger(__name__)

# How close a GPX point must be to an edge to count as a match (metres)
SNAP_RADIUS_M = 25

# Confidence increment per GPX route that uses an edge
BOOST_PER_ROUTE = 0.05

# Maximum accumulated boost
MAX_BOOST = 0.40


def _load_track_points(gpx_path: Path) -> list[tuple[float, float]]:
    """
    Parse a GPX file and return all track points as (lon, lat) tuples.

    Args:
        gpx_path: Path to the .gpx file.

    Returns:
        List of (lon, lat) tuples from all track segments.
    """
    points = []
    try:
        with gpx_path.open("r", encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    points.append((pt.longitude, pt.latitude))
    except Exception as exc:
        logger.warning("Failed to parse GPX %s: %s", gpx_path, exc)
    return points


def _find_matched_edge_ids(
    points: list[tuple[float, float]],
    subregion: str,
    db: Session,
    sample_every: int = 5,
) -> set[int]:
    """
    Find graph edge IDs that are within SNAP_RADIUS_M of track points.

    Samples every Nth point to reduce query volume (GPX tracks are dense).

    Args:
        points: List of (lon, lat) track points.
        subregion: Subregion filter for edge lookup.
        db: SQLAlchemy session.
        sample_every: Take one point per N for performance.

    Returns:
        Set of matched edge IDs.
    """
    matched: set[int] = set()
    sampled = points[::sample_every]

    for lon, lat in sampled:
        pt_geog = cast(ST_MakePoint(lon, lat), Geography)
        edge_geog = cast(Edge.geom, Geography)

        rows = db.execute(
            select(Edge.id).where(
                Edge.subregion == subregion,
                ST_DWithin(edge_geog, pt_geog, SNAP_RADIUS_M),
            )
        ).scalars().all()

        matched.update(rows)

    return matched


def _apply_boost(edge_ids: set[int], db: Session) -> int:
    """
    Increment rwgps_confidence_boost on matched edges, capped at MAX_BOOST.

    Args:
        edge_ids: Set of edge DB IDs to boost.
        db: SQLAlchemy session.

    Returns:
        Number of edges actually updated.
    """
    if not edge_ids:
        return 0

    db.execute(
        update(Edge)
        .where(Edge.id.in_(list(edge_ids)))
        .values(
            rwgps_confidence_boost=func.least(
                func.coalesce(Edge.rwgps_confidence_boost, 0.0) + BOOST_PER_ROUTE,
                MAX_BOOST,
            )
        )
    )
    db.commit()
    return len(edge_ids)


def ingest_rwgps_directory(
    subregion: str,
    gpx_dir: str,
    db: Session,
    reset: bool = False,
) -> dict:
    """
    Process all .gpx files in a directory and apply edge confidence boosts.

    Args:
        subregion: One of "marin", "point_reyes", "sonoma_south".
        gpx_dir: Path to directory containing .gpx files.
        db: SQLAlchemy session.
        reset: If True, clear all existing rwgps_confidence_boost for this
               subregion before processing (start fresh).

    Returns:
        Stats dict: {"files": int, "total_points": int, "edges_boosted": int}
    """
    if subregion not in SUBREGION_BBOXES:
        raise ValueError(f"Unknown subregion '{subregion}'")

    gpx_path = Path(gpx_dir)
    if not gpx_path.is_dir():
        raise ValueError(f"GPX directory not found: {gpx_dir}")

    gpx_files = sorted(gpx_path.glob("*.gpx"))
    if not gpx_files:
        logger.warning("No .gpx files found in %s", gpx_dir)
        return {"files": 0, "total_points": 0, "edges_boosted": 0}

    if reset:
        logger.info("Resetting rwgps_confidence_boost for subregion '%s'...", subregion)
        db.execute(
            update(Edge)
            .where(Edge.subregion == subregion)
            .values(rwgps_confidence_boost=None)
        )
        db.commit()

    logger.info(
        "Processing %d GPX files for subregion '%s' (snap radius: %d m, boost per route: %.2f)...",
        len(gpx_files), subregion, SNAP_RADIUS_M, BOOST_PER_ROUTE,
    )

    total_points = 0
    total_boosted_edges: set[int] = set()

    for i, gpx_file in enumerate(gpx_files, 1):
        points = _load_track_points(gpx_file)
        if not points:
            logger.debug("Skipping empty/invalid GPX: %s", gpx_file.name)
            continue

        total_points += len(points)
        matched = _find_matched_edge_ids(points, subregion, db)
        n_boosted = _apply_boost(matched, db)
        total_boosted_edges.update(matched)

        logger.info(
            "  [%d/%d] %s — %d points, %d edges matched",
            i, len(gpx_files), gpx_file.name, len(points), n_boosted,
        )

    logger.info(
        "RWGPS ingest complete for '%s': %d files, %d points, %d unique edges boosted.",
        subregion, len(gpx_files), total_points, len(total_boosted_edges),
    )
    return {
        "files": len(gpx_files),
        "total_points": total_points,
        "edges_boosted": len(total_boosted_edges),
    }
