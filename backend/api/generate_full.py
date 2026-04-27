"""
POST /api/generate-full  (v2 — corridor-first, Mapbox-powered)

Replaces the old NetworkX/campsite-first pipeline with:
  1. Claude parses the natural-language prompt + structured UI preferences
  2. Corridor planner designs 3 differentiated route archetypes
  3. Mapbox Directions API routes each corridor (fast, any geography)
  4. Strava Segments API enriches corridors with popular community roads
  5. Claude generates a rich trip narrative for each route
  6. Response includes full geometry, day-by-day itinerary, overnight stops,
     and AI-written trip guide

Key changes from v1:
  - GenerateFullRequest now accepts structured rider_profile and trip_preferences
    from the UI (not just a raw text prompt)
  - No more NetworkX graph loading (eliminates the 30-60s startup delay)
  - Routes are generated in ~3-5s instead of 30-90s
  - Geography is no longer limited to North Bay — any location works
"""

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.models import TripRequest
from backend.db.session import get_db
from backend.modules.parser.intent_parser import parse_trip_request, validate_trip_spec
from backend.modules.planner.corridor_planner import plan_routes, PlannedRoute
from backend.modules.ai.trip_narrator import generate_narratives_for_routes
from backend.modules.routing.mapbox_router import get_usage_today, MapboxBudgetExceeded
from backend.api.gpx_inline import store_route_geometry
from backend.schemas.trip_spec import TripSpec, RiderProfile, TripPreferences

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RiderProfileInput(BaseModel):
    """Structured rider profile from the UI — mirrors the TripSpec RiderProfile."""
    fitness_level: str = "intermediate"
    technical_skill: str = "medium"
    overnight_experience: str = "some"
    comfort_daily_km: float = 75.0
    comfort_daily_climbing_m: float = 1200.0
    remote_tolerance: str = "medium"
    bailout_preference: str = "medium"


class TripPreferencesInput(BaseModel):
    """Structured trip preferences from the UI."""
    scenic: bool = False
    minimize_traffic: bool = True
    prefer_remote: bool = False
    hotel_allowed: bool = False
    camping_required: bool = True
    gravel_ratio: float = Field(default=0.5, ge=0.0, le=1.0)


class GenerateFullRequest(BaseModel):
    """
    v2 request body — accepts both the natural-language prompt AND structured
    UI preferences. The structured preferences are used as hard constraints;
    Claude only parses the prompt for nuances and overrides.
    """
    prompt: str = Field(..., min_length=5, max_length=2000)
    # Optional structured inputs from the UI (if provided, override Claude's inferences)
    rider_profile: Optional[RiderProfileInput] = None
    trip_preferences: Optional[TripPreferencesInput] = None
    # Optional: explicit origin override (e.g. "Fairfax, CA")
    origin: Optional[str] = None
    # Optional: explicit number of days override
    days: Optional[int] = Field(default=None, ge=1, le=14)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _build_route_data_for_narrative(
    route: PlannedRoute,
    spec: TripSpec,
    request_id: str,
) -> dict:
    """Build the data dict passed to the AI narrative generator."""
    return {
        "request_id": request_id,
        "archetype": route.archetype,
        "metrics": {
            "total_distance_km": route.total_distance_km,
            "total_climbing_m": route.total_climbing_m,
            "gravel_ratio": route.gravel_ratio,
            "trip_days": route.trip_days,
        },
        "rider_profile": {
            "fitness_level": spec.rider_profile.fitness_level,
            "technical_skill": spec.rider_profile.technical_skill,
            "comfort_daily_km": spec.rider_profile.comfort_daily_km,
            "comfort_daily_climbing_m": spec.rider_profile.comfort_daily_climbing_m,
        },
        "day_plans": [
            {
                "day": seg.day_number,
                "distance_km": seg.distance_km,
                "climbing_m": seg.climbing_m,
                "gravel_ratio": seg.gravel_ratio,
                "overnight_name": seg.overnight_name or "overnight stop",
                "overnight_type": seg.overnight_type or "campsite",
            }
            for seg in route.day_segments
        ],
        "strava_highlights": route.strava_highlights,
        "preferences": {
            "scenic": spec.preferences.scenic,
            "minimize_traffic": spec.preferences.minimize_traffic,
            "prefer_remote": spec.preferences.prefer_remote,
        },
    }


def _map_day_segment(seg, narrative_day: Optional[dict] = None) -> dict:
    """Convert a DaySegment to the frontend DaySegment shape."""
    overnight_area = None
    if seg.overnight_name and seg.overnight_coord:
        lat, lon = seg.overnight_coord
        overnight_area = {
            "name": seg.overnight_name,
            "description": f"{(seg.overnight_type or 'campsite').replace('_', ' ').capitalize()} stop",
            "coordinates": [lat, lon],
            "options": [{
                "id": f"overnight-{seg.day_number}",
                "name": seg.overnight_name,
                "type": seg.overnight_type or "campsite",
                "distance_from_route_km": 0.0,
                "description": seg.overnight_name,
                "amenities": [],
                "coordinates": [lat, lon],
            }],
            "framing_note": "",
        }

    headline = narrative_day.get("headline", f"Day {seg.day_number}") if narrative_day else f"Day {seg.day_number}"
    description = narrative_day.get("narrative", "") if narrative_day else (
        f"{seg.distance_km} km with {seg.climbing_m:.0f} m of climbing."
    )
    key_advice = narrative_day.get("key_advice", "") if narrative_day else ""

    # Structured water and grocery points from AI narrative
    raw_water = narrative_day.get("water_points", []) if narrative_day else []
    raw_grocery = narrative_day.get("grocery_points", []) if narrative_day else []

    def _normalise_points(raw: list) -> list:
        """Accept both plain strings and {name, distance_from_day_start_km, confidence} dicts."""
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append({"name": item, "distance_from_day_start_km": None, "confidence": "unverified"})
            elif isinstance(item, dict):
                out.append({
                    "name": item.get("name", "Unknown"),
                    "distance_from_day_start_km": item.get("distance_from_day_start_km"),
                    "confidence": item.get("confidence", "likely"),
                })
        return out

    water_points = _normalise_points(raw_water)
    grocery_points = _normalise_points(raw_grocery)

    return {
        "day": seg.day_number,
        "title": headline,
        "distance_km": seg.distance_km,
        "climbing_m": int(seg.climbing_m),
        "gravel_ratio": seg.gravel_ratio,
        "estimated_hours": seg.estimated_hours,
        "description": description,
        "key_advice": key_advice,
        "highlights": [],
        "terrain_notes": [],
        "overnight_area": overnight_area,
        "water_points": water_points,
        "grocery_points": grocery_points,
    }


def _map_route_to_response(
    route: PlannedRoute,
    narrative: dict,
    spec: TripSpec,
    request_id: str,
    rank: int,
) -> dict:
    """Convert a PlannedRoute + narrative to the frontend RouteOption shape."""

    # Map geometry: frontend Leaflet expects [lat, lon]; GeoJSON is [lon, lat]
    geometry = [[coord[1], coord[0]] for coord in route.full_geometry_coords]

    # Match narrative day entries to day segments
    narrative_days = {d["day"]: d for d in narrative.get("day_narratives", [])}
    day_segments = [
        _map_day_segment(seg, narrative_days.get(seg.day_number))
        for seg in route.day_segments
    ]

    overnight_areas = [
        {
            "name": seg.overnight_name or f"Night {seg.day_number}",
            "description": f"Night {seg.day_number} overnight stop",
            "coordinates": list(seg.overnight_coord) if seg.overnight_coord else [0, 0],
            "options": [],
            "framing_note": "",
        }
        for seg in route.day_segments[:-1]
        if seg.overnight_name
    ]

    route_id = f"{request_id}-{rank}"
    gpx_url = f"/api/gpx/{route_id}"

    return {
        "id": route_id,
        "archetype": route.archetype,
        "archetype_label": route.archetype_label,
        "archetype_tagline": route.archetype_tagline,

        # AI-generated narrative fields
        "trip_title": narrative.get("trip_title", route.archetype_label),
        "summary": narrative.get("terrain_summary", ""),
        "why_this_route": narrative.get("why_this_fits_you", ""),
        "tagline": narrative.get("tagline", route.archetype_tagline),
        "tradeoff_statement": narrative.get("tradeoff_statement", ""),
        "logistics_note": narrative.get("logistics_note", ""),
        "confidence_framing": narrative.get("confidence_framing", ""),

        # Metrics
        "total_distance_km": round(route.total_distance_km, 1),
        "total_climbing_m": int(route.total_climbing_m),
        "gravel_ratio": round(route.gravel_ratio, 2),
        "estimated_days": route.trip_days,

        # Score breakdown (simplified — no longer from NetworkX scorer)
        "score_breakdown": {
            "scenery": 0.8 if route.archetype == "scenic" else 0.6,
            "gravel_quality": 0.75,
            "safety": 0.8 if route.archetype == "easier" else 0.65,
            "logistics": 0.7,
            "overall": 0.75,
        },

        # Structured content
        "day_segments": day_segments,
        "overnight_areas": overnight_areas,
        "strava_highlights": route.strava_highlights,

        # Logistics
        "grocery_distance_km": 5.0,
        "water_distance_km": 2.0,
        "hotel_fallback_distance_km": 5.0,
        "bailout_notes": [],

        # Confidence
        "confidence_notes": route.confidence_notes,
        "confidence_level": route.confidence_level,
        "confidence_details": [
            {
                "aspect": "Routing engine",
                "level": "high",
                "note": "Route geometry from Mapbox Directions API",
            },
            {
                "aspect": "Community validation",
                "level": "high" if route.strava_highlights else "medium",
                "note": (
                    f"Route passes through {len(route.strava_highlights)} popular Strava segments"
                    if route.strava_highlights
                    else "No Strava segment data available for this area"
                ),
            },
        ],

        # Rider fit (derived from narrative)
        "rider_fit_reasons": [
            {"icon_type": "check", "text": narrative.get("why_this_fits_you", "")[:100]},
        ],
        "tradeoffs": [
            {
                "label": "Route character",
                "pro": narrative.get("tagline", ""),
                "con": narrative.get("tradeoff_statement", ""),
            }
        ],

        # Map data
        "geometry": geometry,
        "gpx_url": gpx_url,
        "mapbox_profile": route.mapbox_profile,
    }


def _map_trip_context(spec: TripSpec, usage: dict) -> dict:
    """Build the frontend TripContext dict."""
    region_labels = {
        "north_bay": "North Bay, CA",
        "marin": "Marin County, CA",
        "point_reyes": "Point Reyes, CA",
        "sonoma": "Sonoma County, CA",
    }
    return {
        "parsed_region": region_labels.get(spec.region, spec.region.replace("_", " ").title()),
        "parsed_duration": f"{spec.trip_days.min}–{spec.trip_days.max} days",
        "parsed_distance": f"{spec.total_distance_km.min:.0f}–{spec.total_distance_km.max:.0f} km",
        "parsed_gravel_target": f"{spec.surface_target.gravel_ratio * 100:.0f}% gravel",
        "key_constraints": (spec.hard_constraints or [])[:5],
        "mapbox_usage": usage,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/generate-full")
def generate_full(body: GenerateFullRequest, db: Session = Depends(get_db)):
    """
    v2 endpoint: parse → plan corridors → Mapbox route → Strava enrich → AI narrative.

    Accepts both a natural-language prompt and optional structured UI preferences.
    Returns 3 differentiated route options with full geometry and AI trip guides.
    """
    request_id = str(uuid.uuid4())
    logger.info("generate-full v2 request_id=%s", request_id)

    # Step 1 — Check Mapbox budget before doing any work
    usage = get_usage_today()
    if usage["remaining"] < 3:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Mapbox daily request budget nearly exhausted "
                f"({usage['count']}/{usage['limit']} used). "
                "The cap resets at midnight UTC."
            ),
        )

    # Step 2 — Parse the natural-language prompt via Claude
    try:
        spec_dict = parse_trip_request(body.prompt)
    except Exception as exc:
        logger.exception("Intent parser failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"Failed to parse trip request: {exc}")

    # Step 3 — Override with structured UI inputs if provided
    if body.rider_profile:
        spec_dict["rider_profile"] = body.rider_profile.model_dump()
    if body.trip_preferences:
        spec_dict.setdefault("preferences", {})
        spec_dict["preferences"]["scenic"] = body.trip_preferences.scenic
        spec_dict["preferences"]["minimize_traffic"] = body.trip_preferences.minimize_traffic
        spec_dict["preferences"]["prefer_remote"] = body.trip_preferences.prefer_remote
        spec_dict.setdefault("overnight", {})
        spec_dict["overnight"]["hotel_allowed"] = body.trip_preferences.hotel_allowed
        spec_dict["overnight"]["camping_required"] = body.trip_preferences.camping_required
        spec_dict.setdefault("surface_target", {})
        spec_dict["surface_target"]["gravel_ratio"] = body.trip_preferences.gravel_ratio
    if body.origin:
        spec_dict["origin_preference"] = body.origin
    if body.days:
        spec_dict.setdefault("trip_days", {})
        spec_dict["trip_days"]["min"] = body.days
        spec_dict["trip_days"]["max"] = body.days

    validation_errors = validate_trip_spec(spec_dict)
    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid trip spec: {'; '.join(validation_errors)}",
        )

    try:
        spec = TripSpec.model_validate(spec_dict)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"TripSpec validation error: {exc}")

    # Step 4 — Persist TripRequest (best-effort — skipped if DB unavailable)
    if db is not None:
        db_request = TripRequest(
            id=request_id,
            raw_prompt=body.prompt,
            parsed_constraints_json=spec_dict,
            rider_profile_json=spec_dict.get("rider_profile"),
            region=spec.region,
        )
        db.add(db_request)
        db.commit()

    # Step 5 — Run the corridor-first planning pipeline
    from backend.config import settings as _settings
    try:
        planned_routes = plan_routes(
            spec=spec,
            mapbox_token=_settings.mapbox_token or os.environ.get("MAPBOX_TOKEN", ""),
            strava_token=_settings.strava_access_token or os.environ.get("STRAVA_ACCESS_TOKEN", ""),
            db=db,
        )
    except MapboxBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        logger.exception("Planning pipeline error for request_id=%s: %s", request_id, exc)
        raise HTTPException(status_code=500, detail=f"Planning pipeline error: {exc}")

    if not planned_routes:
        return {
            "request_id": request_id,
            "trip_context": _map_trip_context(spec, get_usage_today()),
            "routes": [],
            "no_results_reason": (
                "No valid routes could be generated. "
                "Check that your Mapbox token is valid and the origin location is accessible."
            ),
        }

    # Step 6 — Generate AI narratives for all routes
    routes_data = [
        _build_route_data_for_narrative(route, spec, request_id)
        for route in planned_routes
    ]
    try:
        narratives = generate_narratives_for_routes(
            routes_data,
            api_key=_settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        )
    except Exception as exc:
        logger.warning("Narrative generation failed: %s — using template fallback", exc)
        from backend.modules.ai.trip_narrator import _template_fallback
        narratives = [_template_fallback(rd) for rd in routes_data]

    # Step 7 — Map to frontend response shape
    route_options = []
    for rank, (route, narrative) in enumerate(zip(planned_routes, narratives)):
        try:
            option = _map_route_to_response(route, narrative, spec, request_id, rank)
            # Store geometry in cache so /api/gpx/{route_id} can serve it
            store_route_geometry(
                option["id"],
                option["geometry"],
                {
                    "trip_title": option.get("trip_title", ""),
                    "total_distance_km": option.get("total_distance_km", 0),
                    "total_climbing_m": option.get("total_climbing_m", 0),
                    "gravel_ratio": option.get("gravel_ratio", 0),
                    "overnight_areas": option.get("overnight_areas", []),
                },
            )
            route_options.append(option)
        except Exception as exc:
            logger.warning("Failed to map route %d: %s", rank, exc)

    return {
        "request_id": request_id,
        "trip_context": _map_trip_context(spec, get_usage_today()),
        "routes": route_options,
    }


# ---------------------------------------------------------------------------
# Usage / health endpoint
# ---------------------------------------------------------------------------

@router.get("/mapbox-usage")
def mapbox_usage():
    """Return current Mapbox API usage stats. Safe to expose in the UI."""
    return get_usage_today()
