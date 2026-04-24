"""
POST /api/parse

Accepts a natural-language bikepacking request and returns a structured TripSpec.
This is the entry point for all trip planning — nothing downstream runs until this succeeds.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import TripRequest
from backend.modules.parser.intent_parser import parse_trip_request, validate_trip_spec
from backend.schemas.trip_spec import ParseRequest, ParseResponse, TripSpec

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/parse", response_model=ParseResponse)
def parse(body: ParseRequest, db: Session = Depends(get_db)) -> ParseResponse:
    """
    Parse a natural-language trip request into a structured TripSpec.

    Returns a request_id that must be passed to /api/generate.
    Returns 400 if the parsed spec fails validation.
    """
    request_id = str(uuid.uuid4())
    logger.info("parse request_id=%s prompt=%.80s...", request_id, body.prompt)

    # Call Claude parser
    try:
        raw_spec = parse_trip_request(body.prompt)
    except Exception as exc:
        logger.exception("Parser call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Parser error: {exc}")

    # Validate logical consistency
    errors = validate_trip_spec(raw_spec)
    if errors:
        logger.warning("parse validation errors: %s", errors)
        raise HTTPException(status_code=400, detail={"validation_errors": errors})

    # Deserialize into Pydantic model (catches schema mismatches)
    try:
        trip_spec = TripSpec.model_validate(raw_spec)
    except Exception as exc:
        logger.exception("TripSpec schema validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Schema validation error: {exc}")

    # Persist the request (best-effort — skipped if DB unavailable)
    if db is not None:
        db_request = TripRequest(
            id=request_id,
            raw_prompt=body.prompt,
            parsed_constraints_json=raw_spec,
            rider_profile_json=raw_spec.get("rider_profile"),
            region=trip_spec.region,
        )
        db.add(db_request)
        db.commit()

    logger.info(
        "parse complete request_id=%s region=%s days=%s-%s dist=%.0f-%.0f km",
        request_id,
        trip_spec.region,
        trip_spec.trip_days.min,
        trip_spec.trip_days.max,
        trip_spec.total_distance_km.min,
        trip_spec.total_distance_km.max,
    )

    warnings = []
    if trip_spec.region not in {"north_bay", "marin", "point_reyes", "sonoma"}:
        warnings.append(f"Region '{trip_spec.region}' is not yet supported. Results may be unavailable.")

    return ParseResponse(
        request_id=request_id,
        trip_spec=trip_spec,
        validation_warnings=warnings,
    )
