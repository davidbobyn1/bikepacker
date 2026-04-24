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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import parse, generate, generate_full, finalize, routes, gpx_inline
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://bikepacker-uezr.vercel.app",
        "https://bikepacker.vercel.app",
    ],
    allow_origin_regex=r"https://bikepacker.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(parse.router, prefix="/api", tags=["parse"])
app.include_router(generate.router, prefix="/api", tags=["generate"])
app.include_router(generate_full.router, prefix="/api", tags=["generate"])
app.include_router(finalize.router, prefix="/api", tags=["finalize"])
app.include_router(routes.router, prefix="/api", tags=["routes"])
app.include_router(gpx_inline.router, prefix="/api", tags=["gpx"])

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
