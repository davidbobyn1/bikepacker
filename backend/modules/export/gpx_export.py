"""
GPX export — Phase 11.

Converts an AssembledTrip into a GPX file using gpxpy.
The GPX contains:
  - One track segment with all route coordinates
  - Waypoints for each overnight stop (with name and type annotations)
"""

import logging
from datetime import datetime

import gpxpy
import gpxpy.gpx

from backend.modules.planner.trip_assembler import AssembledTrip

logger = logging.getLogger(__name__)


def export_trip_gpx(trip: AssembledTrip, trip_name: str = "Bikepacking Trip") -> str:
    """
    Serialize an AssembledTrip to a GPX XML string.

    Args:
        trip: Assembled and scored trip candidate.
        trip_name: Human-readable name for the GPX track.

    Returns:
        GPX XML as a string, ready to write to a .gpx file.
    """
    gpx = gpxpy.gpx.GPX()
    gpx.name = trip_name
    gpx.description = (
        f"{trip.trip_days}-day trip | "
        f"{trip.metrics.total_distance_km:.1f} km | "
        f"+{trip.metrics.total_climbing_m:.0f} m climbing | "
        f"{trip.metrics.gravel_ratio * 100:.0f}% gravel"
    )
    gpx.author_name = "Bikepacking Planner"
    gpx.time = datetime.utcnow()

    # --- Track ---
    track = gpxpy.gpx.GPXTrack()
    track.name = trip_name
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    for lon, lat in trip.geometry_coords:
        segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon))

    logger.info(
        "GPX track built: %d points, %.1f km",
        len(segment.points), trip.metrics.total_distance_km,
    )

    # --- Waypoints for overnight stops ---
    cumulative_km = 0.0
    for day_plan in trip.day_plans:
        if day_plan.overnight is None:
            continue

        # Accumulate distance to this overnight
        cumulative_km += day_plan.leg.metrics.distance_km

        poi = day_plan.overnight.poi
        from geoalchemy2.shape import to_shape
        pt = to_shape(poi.geom)

        wpt = gpxpy.gpx.GPXWaypoint(
            latitude=pt.y,
            longitude=pt.x,
            name=poi.name or f"Night {day_plan.day_number} camp",
            description=(
                f"Night {day_plan.day_number} | "
                f"Type: {day_plan.overnight.overnight_type} | "
                f"Tier: {day_plan.overnight.tier} | "
                f"~{cumulative_km:.1f} km from start"
            ),
        )
        gpx.waypoints.append(wpt)
        logger.info(
            "Waypoint added: %s (night %d, %.1f km from start)",
            poi.name or "unnamed", day_plan.day_number, cumulative_km,
        )

    xml = gpx.to_xml()
    logger.info("GPX export complete: %d bytes", len(xml))
    return xml
