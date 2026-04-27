"""
POST /api/refine

Fast-path AI reasoning for route refinement requests.

Given a route + a natural-language instruction (e.g. "Make day 2 shorter"),
Claude returns:
  - reasoning: why the change makes sense
  - proposed_changes: a list of specific, actionable changes
  - feasibility: "easy" | "moderate" | "requires_reroute"

The frontend shows this as a conversational reply with an Apply/Dismiss UI.
Full re-routing on Apply is a future TODO — for now the endpoint returns
reasoning only (no geometry changes).
"""

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class RefineRequest(BaseModel):
    route: dict = Field(..., description="The full RouteOption JSON from the frontend")
    instruction: str = Field(..., min_length=3, max_length=500)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)


class ProposedChange(BaseModel):
    description: str
    impact: str  # e.g. "Reduces day 2 by ~15 km"


class RefineResponse(BaseModel):
    reasoning: str
    proposed_changes: list[ProposedChange]
    feasibility: str  # "easy" | "moderate" | "requires_reroute"
    follow_up_prompt: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert bikepacking trip guide helping a rider refine their route.
You give honest, practical advice grounded in the route data provided.
You never invent terrain, distances, or facilities that aren't in the data.
Keep responses concise — riders read on mobile."""


def _build_refine_prompt(route: dict, instruction: str, history: list[ConversationMessage]) -> str:
    # Summarise the route compactly to avoid token bloat
    days = route.get("estimated_days", "?")
    dist = route.get("total_distance_km", "?")
    climb = route.get("total_climbing_m", "?")
    title = route.get("trip_title") or route.get("archetype_label", "this route")

    day_summaries = []
    for seg in route.get("day_segments", []):
        day_summaries.append(
            f"  Day {seg.get('day')}: {seg.get('distance_km')} km, "
            f"{seg.get('climbing_m')} m climb, "
            f"overnight at {seg.get('overnight_area', {}).get('name', 'unknown') if seg.get('overnight_area') else 'unknown'}"
        )

    route_summary = (
        f"Route: {title}\n"
        f"Total: {dist} km over {days} days, {climb} m climbing\n"
        f"Day breakdown:\n" + "\n".join(day_summaries)
    )

    history_text = ""
    if history:
        history_text = "\n\nPrevious conversation:\n" + "\n".join(
            f"{m.role.capitalize()}: {m.content}" for m in history[-4:]  # last 4 turns
        )

    return f"""A rider wants to refine their bikepacking route. Here is the route data:

{route_summary}{history_text}

Rider's request: "{instruction}"

Respond with a JSON object:
{{
  "reasoning": "1-2 sentences explaining what the change involves and whether it's straightforward",
  "proposed_changes": [
    {{"description": "Specific change to make", "impact": "What this does to the route stats"}},
    {{"description": "Another change if needed", "impact": "Impact"}}
  ],
  "feasibility": "easy" | "moderate" | "requires_reroute",
  "follow_up_prompt": "Optional: a follow-up question to clarify the rider's intent, or null"
}}

feasibility guide:
- "easy": can be done by adjusting pace/start time, no rerouting needed
- "moderate": requires minor waypoint changes, same overall corridor
- "requires_reroute": fundamentally changes the route shape or distance

Return only valid JSON. No markdown, no preamble."""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/refine", response_model=RefineResponse, tags=["refine"])
async def refine_route(body: RefineRequest):
    """
    Fast-path AI reasoning for a route refinement instruction.
    Returns proposed changes and feasibility assessment.
    Full re-routing on Apply is a future TODO.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — returning mock response")
        return _mock_response(body.instruction)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — returning mock response")
        return _mock_response(body.instruction)

    model = os.environ.get("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_refine_prompt(
                    body.route, body.instruction, body.conversation_history
                )}
            ],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return RefineResponse(
            reasoning=data.get("reasoning", ""),
            proposed_changes=[
                ProposedChange(**c) for c in data.get("proposed_changes", [])
            ],
            feasibility=data.get("feasibility", "moderate"),
            follow_up_prompt=data.get("follow_up_prompt"),
        )
    except Exception as exc:
        logger.warning("Refine AI call failed: %s — using mock", exc)
        return _mock_response(body.instruction)


def _mock_response(instruction: str) -> RefineResponse:
    """Fallback mock when Claude is unavailable."""
    return RefineResponse(
        reasoning=f"Your request to '{instruction}' is noted. Here are the changes I'd suggest based on the current route data.",
        proposed_changes=[
            ProposedChange(
                description="Adjust the day boundary to redistribute distance",
                impact="Balances daily effort more evenly"
            ),
            ProposedChange(
                description="Check overnight options near the new day-end point",
                impact="Ensures accommodation is available at the adjusted stop"
            ),
        ],
        feasibility="moderate",
        follow_up_prompt="Would you like me to suggest a specific overnight stop near the adjusted day-end point?",
    )
