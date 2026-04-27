"""
Bikepacking Planner — FastAPI application entry point.

Start the server:
    uvicorn backend.main:app --reload

API docs available at:
    http://localhost:8000/docs
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response

from backend.api import parse, generate, generate_full, finalize, routes, gpx_inline, pois, rwgps_export, elevation
from backend.db.models import Base
from backend.db.session import engine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables if they don't exist...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ready.")
    except Exception as exc:
        logger.warning("Could not create database tables: %s", exc)

    logger.info("Bikepacking Planner API is live — routing via Mapbox Directions API.")
    yield


app = FastAPI(
    title="Bikepacking Planner",
    description="AI-native bikepacking trip builder powered by Mapbox, Strava, and Claude.",
    version="2.0.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:5173",
    "https://bikepacker-uezr.vercel.app",
    "https://bikepacker.vercel.app",
}

@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    # Allow any vercel.app subdomain or localhost
    allowed = (
        origin in ALLOWED_ORIGINS
        or origin.endswith(".vercel.app")
        or origin.startswith("http://localhost")
    )
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "600"
        return response
    response = await call_next(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
app.include_router(generate_full.router, prefix="/api", tags=["generate"])
app.include_router(finalize.router, prefix="/api", tags=["finalize"])
app.include_router(routes.router, prefix="/api", tags=["routes"])
app.include_router(gpx_inline.router, prefix="/api", tags=["gpx"])
app.include_router(pois.router, prefix="/api", tags=["pois"])
app.include_router(rwgps_export.router, prefix="/api", tags=["rwgps"])
app.include_router(elevation.router, prefix="/api", tags=["elevation"])

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/api/mapbox-usage", tags=["health"])
def mapbox_usage():
    """Return today's Mapbox API usage count against the daily cap."""
    from backend.modules.routing.mapbox_router import get_usage_stats
    return get_usage_stats()


@app.get("/", tags=["health"])
def root():
    return {"message": "Bikepacking Planner API", "docs": "/docs"}
