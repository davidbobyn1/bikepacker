"""
GET /api/route/{id}
GET /api/route/{id}/gpx

Return finalized route data and GPX download.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CandidateRoute as CandidateRouteORM
from backend.db.models import FinalRoute as FinalRouteORM
from backend.db.session import get_db
from backend.schemas.route import CandidateRoute, FinalRoute, RouteMetrics, RouteSummary
from backend.schemas.poi import OvernightStop

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/candidate/{candidate_id}/gpx")
def candidate_gpx(candidate_id: int, db: Session = Depends(get_db)) -> Response:
    """
    Generate and return a GPX file for a CandidateRoute by its DB id.

    Works directly on CandidateRoute records created by /api/generate-full,
    without requiring a FinalRoute to exist. Geometry is read from the stored
    PostGIS LineString.
    """
    import gpxpy
    import gpxpy.gpx

    row = db.execute(
        select(CandidateRouteORM).where(CandidateRouteORM.id == candidate_id)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail=f"candidate_id {candidate_id} not found")
    if row.geometry is None:
        raise HTTPException(status_code=404, detail="No geometry stored for this candidate")

    gpx = gpxpy.gpx.GPX()
    gpx.name = f"Bikepacking Route {candidate_id}"
    gpx.description = (
        f"{row.total_distance_km:.0f} km, "
        f"{row.total_climbing_m:.0f} m climbing, "
        f"{(row.gravel_ratio or 0) * 100:.0f}% gravel"
        if row.total_distance_km else ""
    )

    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    seg = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(seg)

    shape = to_shape(row.geometry)   # PostGIS LineString stores (lon, lat)
    for lon, lat in shape.coords:
        seg.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon))

    content = gpx.to_xml()
    return Response(
        content=content,
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="route_{candidate_id}.gpx"'
        },
    )


@router.get("/route/{route_id}")
def get_route(route_id: int, db: Session = Depends(get_db)) -> dict:
    """Return finalized route data including summary and metrics."""
    final_orm = db.execute(
        select(FinalRouteORM).where(FinalRouteORM.id == route_id)
    ).scalar_one_or_none()

    if final_orm is None:
        raise HTTPException(status_code=404, detail=f"route_id {route_id} not found")

    candidate_orm = db.execute(
        select(CandidateRouteORM).where(CandidateRouteORM.id == final_orm.candidate_route_id)
    ).scalar_one_or_none()

    summary_dict = final_orm.final_summary_json or {}
    metrics_dict = candidate_orm.route_metrics_json if candidate_orm else {}
    overnight_plan = candidate_orm.overnight_plan_json if candidate_orm else []
    score = candidate_orm.score_breakdown_json if candidate_orm else {}

    return {
        "route_id": route_id,
        "request_id": final_orm.request_id,
        "candidate_route_id": final_orm.candidate_route_id,
        "summary": summary_dict,
        "metrics": metrics_dict,
        "overnight_plan": overnight_plan,
        "score_breakdown": score,
        "gpx_download_url": f"/api/route/{route_id}/gpx",
        "created_at": final_orm.created_at.isoformat() if final_orm.created_at else None,
    }


@router.get("/route/{route_id}/gpx")
def get_gpx(route_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Download the GPX file for a finalized route."""
    final_orm = db.execute(
        select(FinalRouteORM).where(FinalRouteORM.id == route_id)
    ).scalar_one_or_none()

    if final_orm is None:
        raise HTTPException(status_code=404, detail=f"route_id {route_id} not found")

    if not final_orm.gpx_blob_path:
        raise HTTPException(status_code=404, detail="GPX not yet generated for this route")

    gpx_path = Path(final_orm.gpx_blob_path)
    if not gpx_path.exists():
        raise HTTPException(status_code=404, detail="GPX file not found on disk")

    return FileResponse(
        path=str(gpx_path),
        media_type="application/gpx+xml",
        filename=f"bikepacking_route_{route_id}.gpx",
    )
