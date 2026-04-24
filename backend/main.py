"""
Bikepacking Planner — FastAPI application entry point.

Start the server:
    uvicorn backend.main:app --reload

API docs available at:
    http://localhost:8000/docs
"""

import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, distinct
from sqlalchemy.orm import Session

from backend.api import parse, generate, generate_full, finalize, routes, gpx_inline
from backend.db.models import Base, Edge
from backend.db.session import engine
from backend.modules.planner.leg_generator import load_graph, load_merged_graph

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
    logger.info("Enabling PostGIS extension if not present...")
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
        logger.info("PostGIS extension ready.")
    except Exception as exc:
        logger.warning("Could not enable PostGIS extension (may already exist): %s", exc)

    logger.info("Creating database tables if they don't exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")

    # Warm graphs in a background thread so the health check responds immediately.
    # Railway's health check fires within seconds of startup — we can't block it.
    def _warm_graphs():
        try:
            with Session(engine) as db:
                subregions = db.execute(select(distinct(Edge.subregion))).scalars().all()
            subregions = list(subregions)
            for subregion in subregions:
                logger.info("Warming graph cache for '%s'...", subregion)
                with Session(engine) as db:
                    try:
                        load_graph(subregion, db)
                        logger.info("Graph '%s' ready.", subregion)
                    except Exception as exc:
                        logger.warning("Graph warmup failed for '%s': %s", subregion, exc)
            if len(subregions) > 1:
                logger.info("Warming merged supergraph for %s...", subregions)
                with Session(engine) as db:
                    try:
                        load_merged_graph(subregions, db)
                        logger.info("Merged supergraph ready.")
                    except Exception as exc:
                        logger.warning("Merged graph warmup failed: %s", exc)
        except Exception as exc:
            logger.warning("Graph warmup thread failed: %s", exc)

    threading.Thread(target=_warm_graphs, daemon=True).start()
    logger.info("Graph warmup started in background — health check is live.")

    yield


app = FastAPI(
    title="Bikepacking Planner",
    description="AI-native bikepacking trip builder powered by Mapbox, Strava, and Claude.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before production
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
