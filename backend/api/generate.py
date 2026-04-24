"""
POST /api/generate

Runs the full planning pipeline for a parsed TripSpec:
    select_anchors -> assemble_trips -> hard_filters -> soft_scorer -> relaxation

Returns up to 5 ranked CandidateRoute objects and a log of any relaxations applied.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CandidateRoute as CandidateRouteORM
from backend.db.models import TripRequest
from backend.db.session import get_db
from backend.modules.planner.logistics_enricher import _nearest_poi_km
from backend.modules.planner.relaxation import plan_with_relaxation
from backend.schemas.poi import OvernightOption as OvernightOptionSchema
from backend.schemas.poi import OvernightStop, POI as POISchema
from backend.schemas.route import (
    CandidateRoute, GenerateRequest, GenerateResponse, RouteMetrics,
)
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CANDIDATES = 5


def _orm_overnight_to_schema(overnight_orm) -> tuple[OvernightOptionSchema, POISchema]:
    """Convert OvernightOption ORM row + its POI to Pydantic schemas."""
    poi_orm = overnight_orm.poi
    pt = to_shape(poi_orm.geom)

    poi = POISchema(
        id=poi_orm.id,
        type=poi_orm.type,
        lat=pt.y,
        lon=pt.x,
        name=poi_orm.name,
        source=poi_orm.source,
        metadata=poi_orm.metadata_json or {},
        confidence_score=poi_orm.confidence_score,
        subregion=poi_orm.subregion,
    )
    opt = OvernightOptionSchema(
        id=overnight_orm.id,
        poi_id=overnight_orm.poi_id,
        overnight_type=overnight_orm.overnight_type,
        tier=overnight_orm.tier,
        legality_type=overnight_orm.legality_type,
        reservation_known=overnight_orm.reservation_known,
        seasonality_known=overnight_orm.seasonality_known,
        exact_site_known=overnight_orm.exact_site_known,
        confidence_score=overnight_orm.confidence_score,
    )
    return opt, poi


def _build_overnight_plan(trip, cumulative_km_by_day: list[float], db) -> list[OvernightStop]:
    """Build OvernightStop list from AssembledTrip day plans, including logistics proximity."""
    stops = []
    for day_plan in trip.day_plans:
        if day_plan.overnight is None:
            continue
        overnight_orm = day_plan.overnight
        opt, poi_schema = _orm_overnight_to_schema(overnight_orm)

        # Logistics proximity queries (already run in enrich_trip_logistics but
        # we need the per-stop values for the OvernightStop schema output)
        grocery_km = _nearest_poi_km(poi_schema.lat, poi_schema.lon, "grocery", db)
        convenience_km = _nearest_poi_km(poi_schema.lat, poi_schema.lon, "convenience_store", db)
        water_km = _nearest_poi_km(poi_schema.lat, poi_schema.lon, "water", db)
        hotel_km = _nearest_poi_km(poi_schema.lat, poi_schema.lon, "hotel", db)

        stops.append(OvernightStop(
            night_number=day_plan.day_number,
            overnight_option=opt,
            poi=poi_schema,
            distance_from_start_km=round(cumulative_km_by_day[day_plan.day_number - 1], 2),
            nearby_grocery_km=min(grocery_km, convenience_km),
            nearby_water_km=water_km,
            nearby_hotel_fallback_km=hotel_km if opt.overnight_type != "hotel" else None,
        ))
    return stops


def _trip_to_candidate(trip, score, request_id: str, db) -> CandidateRoute:
    """Convert AssembledTrip + ScoreBreakdown to CandidateRoute Pydantic schema."""
    m = trip.metrics

    # GeoJSON LineString
    geometry = {
        "type": "LineString",
        "coordinates": [[lon, lat] for lon, lat in trip.geometry_coords],
    }

    # Cumulative km at end of each day
    cumulative = []
    total = 0.0
    for day_plan in trip.day_plans:
        total += day_plan.leg.metrics.distance_km
        cumulative.append(total)

    metrics = RouteMetrics(
        total_distance_km=m.total_distance_km,
        total_climbing_m=m.total_climbing_m,
        total_descending_m=m.total_descending_m,
        gravel_ratio=m.gravel_ratio,
        paved_ratio=m.paved_ratio,
        uncertain_km=m.uncertain_km,
        hike_a_bike_km=m.hike_a_bike_km,
        per_day_distance_km=m.per_day_distance_km,
        per_day_climbing_m=m.per_day_climbing_m,
        traffic_score_avg=m.traffic_avg,
        scenic_score_avg=m.scenic_avg,
        data_quality_score_avg=m.data_quality_avg,
    )

    overnight_plan = _build_overnight_plan(trip, cumulative, db)

    return CandidateRoute(
        request_id=request_id,
        geometry=geometry,
        metrics=metrics,
        overnight_plan=overnight_plan,
        score_breakdown=score,
        passed_hard_filters=True,
        filter_failures=[],
        relaxations_applied=[],
        status="scored",
    )


@router.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest, db: Session = Depends(get_db)) -> GenerateResponse:
    """
    Generate ranked route candidates for a previously parsed trip spec.

    Requires a valid request_id from POST /api/parse.
    Runs the full planning pipeline with automatic constraint relaxation.
    Persists candidates to the database.
    """
    # Load the parsed trip request
    trip_request = db.execute(
        select(TripRequest).where(TripRequest.id == body.request_id)
    ).scalar_one_or_none()

    if trip_request is None:
        raise HTTPException(status_code=404, detail=f"request_id '{body.request_id}' not found")

    if not trip_request.parsed_constraints_json:
        raise HTTPException(status_code=422, detail="No parsed trip spec found for this request")

    # Reconstruct TripSpec
    try:
        spec = TripSpec.model_validate(trip_request.parsed_constraints_json)
    except Exception as exc:
        logger.exception("Failed to reconstruct TripSpec for request_id=%s: %s", body.request_id, exc)
        raise HTTPException(status_code=422, detail=f"TripSpec reconstruction error: {exc}")

    logger.info("generate request_id=%s region=%s", body.request_id, spec.region)

    # Run pipeline with relaxation
    try:
        ranked, relaxations = plan_with_relaxation(spec, db)
    except Exception as exc:
        logger.exception("Pipeline error for request_id=%s: %s", body.request_id, exc)
        raise HTTPException(status_code=500, detail=f"Planning pipeline error: {exc}")

    if not ranked:
        logger.warning("No valid trips found for request_id=%s after relaxation", body.request_id)
        return GenerateResponse(
            request_id=body.request_id,
            candidates=[],
            relaxations_applied=relaxations,
            no_results_reason=(
                "No valid routes found even after constraint relaxation. "
                "Try adjusting distance, surface preference, or overnight requirements."
            ),
        )

    # Take top MAX_CANDIDATES
    top = ranked[:MAX_CANDIDATES]

    # Convert to Pydantic schemas and persist
    candidates = []
    for trip, score in top:
        candidate = _trip_to_candidate(trip, score, body.request_id, db)
        candidates.append(candidate)

        # Build PostGIS LineString from route coords (lon, lat pairs)
        coords = candidate.geometry.get("coordinates", [])
        try:
            route_geom = from_shape(LineString(coords), srid=4326) if len(coords) >= 2 else None
        except Exception:
            route_geom = None

        # Persist to DB
        orm_row = CandidateRouteORM(
            request_id=body.request_id,
            geometry=route_geom,
            total_distance_km=candidate.metrics.total_distance_km,
            total_climbing_m=candidate.metrics.total_climbing_m,
            gravel_ratio=candidate.metrics.gravel_ratio,
            paved_ratio=candidate.metrics.paved_ratio,
            uncertainty_km=candidate.metrics.uncertain_km,
            overnight_plan_json=[s.model_dump() for s in candidate.overnight_plan],
            route_metrics_json=candidate.metrics.model_dump(),
            score_breakdown_json=score.model_dump(),
            passed_filters=True,
            status="scored",
        )
        db.add(orm_row)

    db.flush()  # assign IDs before committing

    # Attach DB IDs to Pydantic models
    db.commit()
    db.refresh(orm_row)  # refresh last to confirm commit

    # Re-query to get all persisted IDs in order
    persisted = db.execute(
        select(CandidateRouteORM)
        .where(CandidateRouteORM.request_id == body.request_id)
        .order_by(CandidateRouteORM.id)
    ).scalars().all()

    for i, row in enumerate(persisted[-len(candidates):]):
        candidates[i].id = row.id

    logger.info(
        "generate complete request_id=%s: %d candidates, %d relaxation steps",
        body.request_id, len(candidates), len(relaxations),
    )

    return GenerateResponse(
        request_id=body.request_id,
        candidates=candidates,
        relaxations_applied=relaxations,
    )
