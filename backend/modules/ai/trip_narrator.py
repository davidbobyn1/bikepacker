"""
backend/modules/ai/trip_narrator.py

AI-native trip narrative generator — the "Guide" layer.

This replaces the thin 3-sentence summary with a rich, structured trip package
that makes the product feel like a knowledgeable human guide rather than a
route calculator.

For each generated route, Claude produces:
  - A compelling trip title and tagline
  - A "Why this fits you" paragraph grounded in the rider's actual profile
  - A day-by-day narrative (not just stats — real guidance)
  - Terrain warnings grounded in the actual metrics
  - Resupply and logistics notes
  - Honest confidence/uncertainty framing
  - Tradeoff reasoning

The key discipline: Claude is given the actual metrics and told to stay grounded
in them. It is explicitly prohibited from inventing scenic quality, surface
character, or traffic levels that aren't in the data.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed — AI narrative will use template fallback")


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert bikepacking trip guide with deep knowledge of
route planning, rider fitness, and outdoor logistics. You write compelling, honest,
and practical trip narratives for cyclists.

Your writing is:
- Grounded in the actual data provided (never invent terrain, scenery, or conditions)
- Honest about tradeoffs and uncertainty
- Practical and actionable (specific advice, not generic platitudes)
- Engaging and inspiring without being hyperbolic
- Concise — riders read on mobile, so every sentence earns its place

You always stay within the facts provided. If a metric is unknown or estimated,
you say so. You never describe a route as "stunning" or "epic" unless the scenic
score data supports it."""


def _build_narrative_prompt(route_data: dict) -> str:
    """Build the user prompt for the trip narrative."""
    return f"""Generate a complete trip narrative for this bikepacking route.

## Route Data (ground truth — stay within these facts)
```json
{json.dumps(route_data, indent=2)}
```

## Output Format
Return a JSON object with exactly these fields:

{{
  "trip_title": "A compelling 4-6 word title for this specific route (not generic)",
  "tagline": "One sentence that captures what makes this route distinctive",
  "why_this_fits_you": "2-3 sentences explaining why this route matches the rider's specific profile, fitness level, and preferences. Reference the actual metrics.",
  "day_narratives": [
    {{
      "day": 1,
      "headline": "Short evocative headline for this day (e.g. 'Into the hills')",
      "narrative": "2-3 sentences describing what the rider will experience. Reference the actual distance, climbing, and surface data. Mention where the rider sleeps that night — if overnight_type is 'campsite' or 'dispersed', note dispersed camping; if 'hotel' or 'motel', mention the nearest town. For the final day (is_final_day=true), mention the return to start.",
      "key_advice": "One specific, actionable tip for this day — e.g. water fill-up timing, gear, or campsite booking advice",
      "water_points": [
        {{"name": "Name of water source (creek, spring, tap, etc.)", "distance_from_day_start_km": 25.0, "confidence": "likely"}}
      ],
      "grocery_points": [
        {{"name": "Name of store or town", "distance_from_day_start_km": 40.0, "confidence": "verified"}}
      ]
    }}
  ],
  "terrain_summary": "1-2 sentences honestly describing the surface and terrain character based on the gravel_ratio and climbing data",
  "logistics_note": "1-2 sentences on resupply, water, and overnight logistics. Mention the overnight type for each night (campsite/dispersed camping/hotel) and whether advance booking is needed. If dispersed camping, note that no reservation is required but local regs apply.",
  "confidence_framing": "1 sentence honestly framing the confidence level of this route recommendation",
  "tradeoff_statement": "1 sentence naming the main tradeoff of choosing this route over the alternatives"
}}

Return only valid JSON. No markdown, no preamble."""


# ---------------------------------------------------------------------------
# Main narrative generation function
# ---------------------------------------------------------------------------

def generate_trip_narrative(
    route_data: dict,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Generate a rich AI trip narrative for a route.

    Args:
        route_data: Dict containing route metrics, rider profile, day plans,
                    overnight stops, and Strava segment highlights.
        model:      Anthropic model name. Defaults to CLAUDE_MODEL env var or
                    claude-3-5-haiku-20241022 (fast and cheap for demo).
        api_key:    Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        Dict with trip_title, tagline, why_this_fits_you, day_narratives,
        terrain_summary, logistics_note, confidence_framing, tradeoff_statement.
        Falls back to a template dict on any error.
    """
    if not _ANTHROPIC_AVAILABLE:
        return _template_fallback(route_data)

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        logger.warning("No Anthropic API key — using template narrative")
        return _template_fallback(route_data)

    model_name = model or os.environ.get("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

    try:
        client = anthropic.Anthropic(api_key=key)
        message = client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_narrative_prompt(route_data)}
            ],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        logger.info("AI narrative generated successfully (model=%s)", model_name)
        return result
    except json.JSONDecodeError as exc:
        logger.warning("AI narrative JSON parse error: %s — using template", exc)
        return _template_fallback(route_data)
    except Exception as exc:
        logger.warning("AI narrative generation failed: %s — using template", exc)
        return _template_fallback(route_data)


def _template_fallback(route_data: dict) -> dict:
    """
    Template-based fallback when Claude is unavailable.
    Uses the actual metrics to produce a factual (if less inspiring) narrative.
    """
    metrics = route_data.get("metrics", {})
    days = route_data.get("trip_days", 2)
    dist = metrics.get("total_distance_km", 0)
    climb = metrics.get("total_climbing_m", 0)
    gravel_pct = round(metrics.get("gravel_ratio", 0.5) * 100)
    archetype = route_data.get("archetype", "scenic")
    rider = route_data.get("rider_profile", {})
    fitness = rider.get("fitness_level", "intermediate")

    day_narratives = []
    for i, day_plan in enumerate(route_data.get("day_plans", []), 1):
        d_km = day_plan.get("distance_km", round(dist / days, 1))
        d_climb = day_plan.get("climbing_m", round(climb / days))
        overnight_name = day_plan.get("overnight_name", "overnight stop")
        day_narratives.append({
            "day": i,
            "headline": f"Day {i} — {d_km} km to {overnight_name}",
            "narrative": (
                f"Cover {d_km} km with {d_climb} m of climbing. "
                f"Approximately {gravel_pct}% of the day is on gravel or unpaved surfaces. "
                f"Overnight near {overnight_name}."
            ),
            "key_advice": "Check water sources before leaving camp each morning.",
        })

    return {
        "trip_title": f"{days}-Day {archetype.capitalize()} Bikepacking Loop",
        "tagline": f"{dist:.0f} km · {climb:.0f} m climbing · {gravel_pct}% gravel",
        "why_this_fits_you": (
            f"This route is designed for a {fitness} rider targeting {dist:.0f} km "
            f"over {days} days with a mixed gravel/paved surface. "
            f"The climbing profile and daily distances align with your stated comfort range."
        ),
        "day_narratives": day_narratives,
        "terrain_summary": (
            f"Approximately {gravel_pct}% of the route is on gravel or unpaved surfaces, "
            f"with {100 - gravel_pct}% on paved roads."
        ),
        "logistics_note": (
            "Water sources and resupply points are noted on the day-by-day map. "
            "Confirm campsite availability before departure."
        ),
        "confidence_framing": (
            "Route data is derived from OpenStreetMap and community sources. "
            "Surface conditions may vary seasonally."
        ),
        "tradeoff_statement": (
            f"This {archetype} option prioritises "
            + ("scenery and terrain variety" if archetype == "scenic"
               else "lower stress and better logistics" if archetype == "easier"
               else "technical challenge and remoteness")
            + " over the alternatives."
        ),
    }


# ---------------------------------------------------------------------------
# Batch narrative generation (for parallel route options)
# ---------------------------------------------------------------------------

def generate_narratives_for_routes(
    routes_data: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Generate narratives for multiple route options.

    Runs sequentially to avoid rate-limiting. For 3 routes this takes ~3-6s
    with claude-3-5-haiku, which is acceptable for a demo.

    Args:
        routes_data: List of route data dicts (one per route option).
        model:       Anthropic model name.
        api_key:     Anthropic API key.

    Returns:
        List of narrative dicts in the same order as routes_data.
    """
    narratives = []
    for i, route_data in enumerate(routes_data):
        logger.info("Generating narrative for route %d/%d", i + 1, len(routes_data))
        narrative = generate_trip_narrative(route_data, model=model, api_key=api_key)
        narratives.append(narrative)
    return narratives
