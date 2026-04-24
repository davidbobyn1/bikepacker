"""
Intent parser — the only place in the codebase where Claude API is called for parsing.

All Claude API calls for trip spec parsing and route summary generation
must go through this module. Do not make ad hoc anthropic client calls elsewhere.
"""

import json
import logging

import anthropic

from backend.config import settings
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ---------------------------------------------------------------------------
# Verbatim system prompt — do not paraphrase or simplify.
# Source: docs/parser_prompt.md
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the intent parser for an AI-native bikepacking trip planner.

Your job is to convert a natural-language bikepacking request into a structured JSON trip specification. You must output only valid JSON — no explanation, no preamble, no markdown code fences.

The JSON must conform exactly to the schema below. Apply all defaults and inferences described. Do not leave required fields empty.

---

OUTPUT SCHEMA:

{
  "region": string,                        // slug for the geographic region, e.g. "north_bay", "cape_cod", "dolomites", "kyoto_area"
                                           // derive from place names mentioned; use snake_case; default: "unknown" if unspecified
  "origin_preference": string | null,      // city or hub name if mentioned, else null

  "trip_days": {
    "min": int,                            // minimum trip days, default 2
    "max": int,                            // maximum trip days, default 3
    "flexibility": "hard" | "soft"        // hard if user said "exactly", soft otherwise
  },

  "total_distance_km": {
    "min": float,
    "max": float,
    "flexibility": "hard" | "soft",
    "relax_to": { "min": float, "max": float }  // widen by 20% for relaxation
  },

  "route_shape": {
    "preferred": "loop" | "out_and_back" | "point_to_point",
    "flexibility": "hard" | "soft"        // soft unless user says "must be a loop"
  },

  "surface_target": {
    "gravel_ratio": float,                 // 0.0–1.0, default 0.5 if unspecified
    "tolerance": float,                    // default 0.15
    "flexibility": "soft"                  // surface ratio is always soft
  },

  "overnight": {
    "camping_required": bool,              // true if user mentions camping, campsites, bivvy
    "hotel_allowed": bool,                 // true if user mentions hotels, motels, or "any accommodation"
    "overnight_flexibility": "hard" | "soft"  // hard if user says "must have legal campsites"
  },

  "rider_profile": {
    "fitness_level": "beginner" | "intermediate" | "strong" | "elite",
    "technical_skill": "low" | "medium" | "high",
    "overnight_experience": "none" | "some" | "experienced",
    "comfort_daily_km": float,            // derive from fitness if not stated (see defaults below)
    "comfort_daily_climbing_m": float,    // derive from fitness if not stated
    "remote_tolerance": "low" | "medium" | "high",
    "bailout_preference": "high" | "medium" | "low"
  },

  "logistics_preferences": {
    "grocery_access_required": bool,       // default false
    "water_access_required": bool,         // default true
    "bailout_access_preferred": bool       // default true
  },

  "preferences": {
    "scenic": bool,                        // true if user mentions views, scenery, coast, nature
    "minimize_traffic": bool,              // default true
    "prefer_remote": bool                  // default false unless user mentions solitude/remote
  },

  "hard_constraints": [string],           // list of non-negotiable requirements user stated explicitly

  "soft_constraints": [string],           // list of preferences user mentioned but did not require

  "relaxation_policy": {
    "allow_distance_widen": bool,          // default true
    "allow_surface_widen": bool,           // default true
    "allow_lower_overnight_tier": bool,    // default true
    "allow_hotel_fallback": bool,          // matches hotel_allowed
    "allow_out_and_back": bool             // default true unless loop was hard constraint
  },

  "parser_notes": string                   // brief note on any inferences or ambiguities you resolved
}

---

RIDER PROFILE DEFAULTS (apply when fitness level is stated but specific numbers are not):

beginner:
  comfort_daily_km: 50
  comfort_daily_climbing_m: 700
  remote_tolerance: low
  bailout_preference: high

intermediate:
  comfort_daily_km: 75
  comfort_daily_climbing_m: 1200
  remote_tolerance: medium
  bailout_preference: medium

strong:
  comfort_daily_km: 110
  comfort_daily_climbing_m: 2000
  remote_tolerance: medium
  bailout_preference: low

elite:
  comfort_daily_km: 150
  comfort_daily_climbing_m: 3000
  remote_tolerance: high
  bailout_preference: low

---

CONSTRAINT CLASSIFICATION RULES:

Mark a constraint as "hard" if the user uses language like:
  "must", "need", "require", "only", "has to", "non-negotiable", "make sure"

Mark a constraint as "soft" if the user uses language like:
  "prefer", "would like", "ideally", "if possible", "try to", "around", "roughly", "maybe"

When ambiguous, default to soft.

---

DISTANCE DEFAULTS:

If distance is not mentioned, infer from trip_days and rider fitness:
  2-day intermediate: 120–160 km
  3-day intermediate: 160–220 km
  2-day beginner: 80–120 km
  3-day beginner: 100–160 km
  2-day strong: 160–220 km
  3-day strong: 220–300 km

---

REGION INFERENCE:
Derive the region slug from any place names the user mentions. Use snake_case. Examples:
  "Marin", "North Bay", "Point Reyes", "Sonoma" → "north_bay"
  "Cape Cod", "Boston" → "cape_cod"
  "Dolomites", "South Tyrol" → "dolomites"
  "Kyoto", "Japan" → "kyoto_area"
  "Scottish Highlands" → "scottish_highlands"
If no region is mentioned, use "unknown". Always parse fully regardless of region.

---

OUTPUT: Valid JSON only. No explanation. No markdown. No extra fields beyond the schema."""


SUMMARY_SYSTEM_PROMPT = """You are a friendly, knowledgeable bikepacking guide. Given a structured route candidate,
write a 3–5 sentence trip summary in plain English. Mention the region, overnight stops,
approximate daily distances, terrain character, and any important caveats or uncertainty warnings.
Be direct and practical. Do not oversell. If overnight confidence is low, say so."""


def parse_trip_request(raw_prompt: str) -> dict:
    """
    Call Claude to parse a natural-language bikepacking request into a TripSpec dict.

    Args:
        raw_prompt: The user's natural-language trip request.

    Returns:
        Parsed TripSpec as a dict (not yet validated).
    """
    logger.info("Calling Claude parser for prompt: %.80s...", raw_prompt)

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": raw_prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    parsed = json.loads(raw.strip())
    logger.info("Parser returned spec for region=%s, days=%s", parsed.get("region"), parsed.get("trip_days"))
    return parsed


def validate_trip_spec(spec: dict) -> list[str]:
    """
    Validate a parsed TripSpec dict for logical consistency.

    Args:
        spec: The dict returned by parse_trip_request.

    Returns:
        List of error strings. Empty list means valid.
    """
    errors = []

    dist = spec.get("total_distance_km", {})
    if dist.get("min", 0) >= dist.get("max", 0):
        errors.append("distance min must be less than max")

    surface = spec.get("surface_target", {})
    gravel = surface.get("gravel_ratio", 0.5)
    if not 0.0 <= gravel <= 1.0:
        errors.append("gravel_ratio must be between 0 and 1")

    days = spec.get("trip_days", {})
    if days.get("min", 2) < 1 or days.get("max", 3) > 7:
        errors.append("trip_days out of supported range (1–7)")

    # Region validation removed — Mapbox routing supports any location worldwide

    rider = spec.get("rider_profile", {})
    if rider.get("comfort_daily_km", 1) <= 0:
        errors.append("comfort_daily_km must be positive")

    return errors


def generate_route_summary(candidate: dict) -> str:
    """
    Call Claude to generate a plain-English route summary.

    Args:
        candidate: A CandidateRoute dict with metrics, overnight plan, and scores.

    Returns:
        A 3–5 sentence route summary string.
    """
    logger.info("Generating route summary for candidate request_id=%s", candidate.get("request_id"))

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=400,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(candidate)}],
    )
    return response.content[0].text.strip()
