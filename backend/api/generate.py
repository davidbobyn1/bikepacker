"""
POST /api/generate  (legacy stub — use /api/generate-full instead)

The v1 NetworkX/campsite-first pipeline has been replaced by the v2
corridor-first Mapbox pipeline. All route generation now goes through
/api/generate-full which is what the frontend calls.

This stub is kept so the router registration in main.py doesn't break.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class LegacyGenerateRequest(BaseModel):
    request_id: str = ""


@router.post("/generate")
def generate(body: LegacyGenerateRequest):
    """
    Legacy endpoint — use /api/generate-full instead.
    The v1 NetworkX routing pipeline has been replaced by Mapbox Directions API.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "This endpoint has been replaced by POST /api/generate-full. "
            "Please use the new endpoint which supports natural language prompts "
            "and Mapbox-powered routing."
        ),
    )
