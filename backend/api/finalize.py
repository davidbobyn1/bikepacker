"""
POST /api/finalize

Finalizes a selected CandidateRoute:
  1. Loads the candidate from DB
  2. Generates a GPX file using gpxpy
  3. Calls Claude to generate a plain-English route summary
  4. Persists a FinalRoute record
  5. Returns the summary and GPX download URL
"""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CandidateRoute as CandidateRouteORM
from backend.db.models import FinalRoute as FinalRouteORM
from backend.db.models import TripRequest
from backend.db.session import get_db
from backend.modules.parser.intent_parser import generate_route_summary
from backend.schemas.route import FinalizeRequest, FinalizeResponse, RouteSummary

logger = logging.getLogger(__name__)
router = APIRouter()

GPX_DIR = Path("gpx_files")


def _ensure_gpx_dir() -> None:
    GPX_DIR.mkdir(exist_ok=True)


@router.post("/finalize", response_model=FinalizeResponse)
def finalize(body: FinalizeRequest, db: Session = Depends(get_db)) -> FinalizeResponse:
    """
    Finalize a selected route candidate.

    Generates GPX and a Claude-authored route summary.
    Returns a download URL for the GPX file.
    """
    _ensure_gpx_dir()

    # Load candidate
    candidate_orm = db.execute(
        select(CandidateRouteORM).where(CandidateRouteORM.id == body.candidate_route_id)
    ).scalar_one_or_none()

    if candidate_orm is None:
        raise HTTPException(status_code=404, detail=f"candidate_route_id {body.candidate_route_id} not found")

    if candidate_orm.request_id != body.request_id:
        raise HTTPException(status_code=403, detail="candidate_route_id does not belong to this request")

    # Load trip request for spec context
    trip_request = db.execute(
        select(TripRequest).where(TripRequest.id == body.request_id)
    ).scalar_one_or_none()

    if trip_request is None:
        raise HTTPException(status_code=404, detail=f"request_id '{body.request_id}' not found")

    # --- GPX generation ---
    import gpxpy
    import gpxpy.gpx
    from datetime import datetime
    from geoalchemy2.shape import to_shape

    gpx = gpxpy.gpx.GPX()
    metrics = candidate_orm.route_metrics_json or {}
    overnight_plan = candidate_orm.overnight_plan_json or []

    total_dist = metrics.get("total_distance_km", 0)
    total_climb = metrics.get("total_climbing_m", 0)
    gravel_pct = round(metrics.get("gravel_ratio", 0) * 100)

    gpx.name = f"Bikepacking Trip - {total_dist:.0f} km"
    gpx.description = (
        f"{total_dist:.1f} km | +{total_climb:.0f} m | {gravel_pct}% gravel"
    )
    gpx.author_name = "Bikepacking Planner"
    gpx.time = datetime.utcnow()

    # --- Track segment from stored PostGIS geometry ---
    if candidate_orm.geometry is not None:
        try:
            line = to_shape(candidate_orm.geometry)
            track = gpxpy.gpx.GPXTrack()
            track.name = gpx.name
            gpx.tracks.append(track)
            segment = gpxpy.gpx.GPXTrackSegment()
            track.segments.append(segment)
            for lon, lat in line.coords:
                segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon))
            logger.info("GPX track: %d points from stored geometry", len(segment.points))
        except Exception as exc:
            logger.warning("Failed to load route geometry for GPX track: %s", exc)

    # --- Overnight waypoints ---
    for stop in overnight_plan:
        poi = stop.get("poi", {})
        lat = poi.get("lat")
        lon = poi.get("lon")
        name = poi.get("name") or f"Night {stop.get('night_number', '?')} camp"
        night = stop.get("night_number", "?")
        dist = stop.get("distance_from_start_km", 0)
        overnight_type = stop.get("overnight_option", {}).get("overnight_type", "campsite")
        tier = stop.get("overnight_option", {}).get("tier", "?")

        if lat is not None and lon is not None:
            wpt = gpxpy.gpx.GPXWaypoint(
                latitude=lat,
                longitude=lon,
                name=name,
                description=f"Night {night} | {overnight_type} (tier {tier}) | ~{dist:.1f} km from start",
            )
            gpx.waypoints.append(wpt)

    gpx_xml = gpx.to_xml()
    gpx_path = GPX_DIR / f"route_{body.candidate_route_id}.gpx"
    gpx_path.write_text(gpx_xml, encoding="utf-8")
    logger.info("GPX written: %s (%d bytes)", gpx_path, len(gpx_xml))

    # --- Claude summary ---
    candidate_dict = {
        "request_id": body.request_id,
        "metrics": metrics,
        "overnight_plan": overnight_plan,
        "score_breakdown": candidate_orm.score_breakdown_json or {},
        "raw_prompt": trip_request.raw_prompt,
    }

    summary_text = ""
    try:
        summary_text = generate_route_summary(candidate_dict)
    except Exception as exc:
        logger.warning("Summary generation failed (non-fatal): %s", exc)
        summary_text = (
            f"A {total_dist:.0f} km {_day_count(overnight_plan)}-day bikepacking loop "
            f"with {gravel_pct}% gravel and +{total_climb:.0f} m of climbing. "
            f"Overnights: {', '.join(s.get('poi', {}).get('name', 'camp') for s in overnight_plan)}."
        )

    summary = RouteSummary(
        headline=_make_headline(metrics, overnight_plan),
        body=summary_text,
        warnings=[],
    )

    # --- Persist FinalRoute ---
    existing = db.execute(
        select(FinalRouteORM).where(FinalRouteORM.candidate_route_id == body.candidate_route_id)
    ).scalar_one_or_none()

    if existing:
        final_orm = existing
        final_orm.gpx_blob_path = str(gpx_path)
        final_orm.final_summary_json = summary.model_dump()
    else:
        final_orm = FinalRouteORM(
            request_id=body.request_id,
            candidate_route_id=body.candidate_route_id,
            gpx_blob_path=str(gpx_path),
            final_summary_json=summary.model_dump(),
        )
        db.add(final_orm)

    db.commit()
    db.refresh(final_orm)

    logger.info(
        "finalize complete request_id=%s candidate_id=%d final_id=%d",
        body.request_id, body.candidate_route_id, final_orm.id,
    )

    return FinalizeResponse(
        route_id=final_orm.id,
        summary=summary,
        gpx_download_url=f"/api/route/{final_orm.id}/gpx",
    )


def _day_count(overnight_plan: list) -> int:
    if not overnight_plan:
        return 1
    return max((s.get("night_number", 1) for s in overnight_plan), default=1) + 1


def _make_headline(metrics: dict, overnight_plan: list) -> str:
    dist = metrics.get("total_distance_km", 0)
    climb = metrics.get("total_climbing_m", 0)
    days = _day_count(overnight_plan)
    gravel = round(metrics.get("gravel_ratio", 0) * 100)
    camps = [s.get("poi", {}).get("name", "camp") for s in overnight_plan]
    camp_str = " & ".join(camps) if camps else "no overnight"
    return f"{days}-day, {dist:.0f} km loop | +{climb:.0f} m | {gravel}% gravel | {camp_str}"
