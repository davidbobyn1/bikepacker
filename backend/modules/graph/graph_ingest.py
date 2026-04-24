"""
Graph ingest — downloads OSM bike graph for a subregion and stores enriched
nodes and edges into PostGIS.

Usage (via script):
    python -m backend.scripts.ingest_graph --subregion marin

Design notes:
- OSMnx downloads two overlapping graphs (bike network + custom trail filter)
  and merges them to capture tracks/paths the bike network misses.
- Elevation is attached if SRTM_RASTER_PATH is set in config. Without it,
  climb_up_m / climb_down_m default to 0 and a warning is logged.
- Ingest is idempotent: existing nodes/edges for a subregion are deleted and
  rewritten on each run, so the script can be rerun after OSM updates.
"""

import logging
from typing import Optional

import networkx as nx
import osmnx as ox
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy.orm import Session

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from backend.modules.graph.graph_enrichment import enrich_edge
from backend.db.models import Edge, Node
from backend.config import settings

logger = logging.getLogger(__name__)

# Bounding boxes per subregion: (west, south, east, north) = (left, bottom, right, top)
#
# IMPORTANT: Marin bbox is intentionally widened to (-123.00, 37.80, -122.40, 38.25).
# The original narrow bbox (-122.65 … -122.45) left a gap at longitude -122.75 to -122.65
# that excluded the primary Fairfax→Point Reyes cycling corridors (Fairfax-Bolinas Road,
# Sir Francis Drake Blvd, Nicasio Valley Road). Without these roads the Marin, Point Reyes,
# and Sonoma South subgraph components had zero shared border nodes and routing between
# them was impossible. The wider bbox overlaps with both Point Reyes and Sonoma South,
# creating shared border nodes that make the merged supergraph fully connected.
SUBREGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "marin":        (-123.00, 37.80, -122.40, 38.25),
    "point_reyes":  (-122.95, 37.95, -122.75, 38.20),
    "sonoma_south": (-122.80, 38.10, -122.40, 38.50),
}

# Custom Overpass filter to capture tracks and paths the bike network misses
CUSTOM_FILTER = (
    '["highway"~"cycleway|track|path|footway|bridleway|unclassified|residential|service"]'
    '["bicycle"!~"no"]["motor_vehicle"!~"yes"]'
)


def download_graph(subregion: str) -> nx.MultiDiGraph:
    """
    Download and merge bike-relevant OSM graphs for a subregion.

    Downloads two graphs:
    1. network_type="bike" — OSMnx's built-in bike network
    2. custom_filter — broader trail/track coverage

    Args:
        subregion: One of the keys in SUBREGION_BBOXES.

    Returns:
        Merged MultiDiGraph with all bike-relevant edges.
    """
    if subregion not in SUBREGION_BBOXES:
        raise ValueError(f"Unknown subregion '{subregion}'. Valid: {list(SUBREGION_BBOXES)}")

    west, south, east, north = SUBREGION_BBOXES[subregion]
    logger.info("Downloading bike graph for %s (N=%.3f S=%.3f E=%.3f W=%.3f)...",
                subregion, north, south, east, west)

    # OSMnx 2.x bbox format: (left, bottom, right, top) = (west, south, east, north)
    bbox = (west, south, east, north)

    try:
        G_bike = ox.graph_from_bbox(
            bbox=bbox,
            network_type="bike",
            retain_all=True,
        )
        logger.info("Bike network: %d nodes, %d edges", len(G_bike.nodes), len(G_bike.edges))
    except Exception as e:
        logger.warning("Bike network download failed (%s), using custom filter only.", e)
        G_bike = None

    logger.info("Downloading custom trail/track graph for %s...", subregion)
    G_custom = ox.graph_from_bbox(
        bbox=bbox,
        custom_filter=CUSTOM_FILTER,
        retain_all=True,
    )
    logger.info("Custom filter graph: %d nodes, %d edges", len(G_custom.nodes), len(G_custom.edges))

    if G_bike is not None:
        G = nx.compose(G_bike, G_custom)
        logger.info("Merged graph: %d nodes, %d edges", len(G.nodes), len(G.edges))
    else:
        G = G_custom

    return G


def _attach_elevation_via_api(G: nx.MultiDiGraph, batch_size: int = 100) -> bool:
    """
    Fetch node elevations from the OpenTopoData SRTM 30m API (free, no key needed).

    Sends nodes in batches of `batch_size` with a short delay between requests
    to stay within the API's rate limit (~1 req/sec).

    Args:
        G: The OSMnx graph to modify in place.
        batch_size: Locations per API request (max 100).

    Returns:
        True if elevations were attached successfully.
    """
    import time
    import requests

    node_ids = list(G.nodes)
    total = len(node_ids)
    logger.info(
        "Fetching elevation for %d nodes via OpenTopoData API "
        "(~%.0f requests, ~%.0f minutes)...",
        total, total / batch_size, total / batch_size / 60,
    )

    url = "https://api.opentopodata.org/v1/srtm30m"
    fetched = 0
    errors = 0
    MAX_RETRIES = 3

    for i in range(0, total, batch_size):
        batch = node_ids[i : i + batch_size]
        locations = "|".join(
            f"{G.nodes[n]['y']},{G.nodes[n]['x']}" for n in batch
        )
        batch_num = i // batch_size
        success = False

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(url, params={"locations": locations}, timeout=30)
                resp.raise_for_status()
                results = resp.json().get("results", [])
                for node_id, result in zip(batch, results):
                    elevation = result.get("elevation")
                    if elevation is not None:
                        G.nodes[node_id]["elevation"] = float(elevation)
                        fetched += 1
                success = True
                break
            except Exception as exc:
                if attempt < MAX_RETRIES - 1:
                    backoff = 2 ** attempt * 2.0  # 2s, 4s
                    logger.debug(
                        "Elevation API batch %d attempt %d failed, retrying in %.0fs: %s",
                        batch_num, attempt + 1, backoff, exc,
                    )
                    time.sleep(backoff)
                else:
                    errors += 1
                    logger.warning(
                        "Elevation API batch %d failed after %d attempts: %s",
                        batch_num, MAX_RETRIES, exc,
                    )

        # Rate limit: ~1 request/second (applied after each successful batch)
        if success:
            time.sleep(1.05)
        # On failure the backoff sleep above already applied; no extra wait needed.

        if batch_num % 20 == 0 and i > 0:
            logger.info("  ... %d / %d nodes fetched", fetched, total)

    logger.info(
        "Elevation API complete: %d / %d nodes fetched, %d batch errors.",
        fetched, total, errors,
    )
    return fetched > 0


def attach_elevation(G: nx.MultiDiGraph, raster_path: Optional[str] = None) -> bool:
    """
    Attach elevation data to graph nodes.

    Priority:
      1. Local SRTM raster if raster_path is provided (fastest, most accurate)
      2. OpenTopoData SRTM 30m API if no raster is configured (free, no key)
      3. Skip with a warning if the API also fails

    Args:
        G: The OSMnx graph to modify in place.
        raster_path: Path to a downloaded SRTM .tif raster file, or None.

    Returns:
        True if elevation was successfully attached.
    """
    if raster_path:
        try:
            ox.elevation.add_node_elevations_raster(G, raster_path)
            ox.elevation.add_edge_grades(G, add_absolute=True)
            logger.info("Elevation attached from raster: %s", raster_path)
            return True
        except Exception as e:
            logger.error("Raster elevation failed: %s — falling back to API.", e)

    # No raster (or raster failed) — use the free OpenTopoData API
    logger.info(
        "No SRTM raster configured — fetching elevation from OpenTopoData API. "
        "Set SRTM_RASTER_PATH in .env to skip this step in future runs."
    )
    success = _attach_elevation_via_api(G)
    if success:
        try:
            # Fill any None elevations (from rate-limited API batches) with 0 so
            # add_edge_grades() doesn't crash on NoneType - NoneType subtraction.
            for _, node_data in G.nodes(data=True):
                if node_data.get("elevation") is None:
                    node_data["elevation"] = 0.0
            ox.elevation.add_edge_grades(G, add_absolute=True)
            logger.info("Edge grades computed from API elevation data.")
        except Exception as e:
            logger.warning("Edge grade computation failed: %s", e)
    else:
        logger.warning(
            "Elevation API failed — climb_up_m and climb_down_m will be 0. "
            "Check your internet connection or set SRTM_RASTER_PATH in .env."
        )
    return success


def _get_edge_geometry(G: nx.MultiDiGraph, u: int, v: int, data: dict) -> LineString:
    """Return edge geometry, falling back to straight line between nodes."""
    geom = data.get("geometry")
    if geom is not None:
        return geom
    # Build straight line from node coordinates
    x_u, y_u = G.nodes[u]["x"], G.nodes[u]["y"]
    x_v, y_v = G.nodes[v]["x"], G.nodes[v]["y"]
    return LineString([(x_u, y_u), (x_v, y_v)])


def _compute_climb(G: nx.MultiDiGraph, u: int, v: int, data: dict, has_elevation: bool) -> tuple[float, float]:
    """
    Compute climb_up_m and climb_down_m for an edge.

    Uses grade attribute if elevation was attached, otherwise 0.
    """
    if not has_elevation:
        return 0.0, 0.0

    grade = data.get("grade", 0.0) or 0.0
    length_m = data.get("length", 0.0) or 0.0
    elevation_diff = grade * length_m

    if elevation_diff > 0:
        return round(elevation_diff, 1), 0.0
    else:
        return 0.0, round(abs(elevation_diff), 1)


def store_graph(
    G: nx.MultiDiGraph,
    subregion: str,
    db: Session,
    has_elevation: bool = False,
    batch_size: int = 500,
) -> dict:
    """
    Store enriched graph nodes and edges into PostGIS.

    Deletes existing nodes/edges for the subregion before reinserting,
    making this safe to re-run after graph updates.

    Args:
        G: The OSMnx MultiDiGraph to store.
        subregion: Subregion name (used as the subregion tag on all rows).
        db: SQLAlchemy session.
        has_elevation: Whether elevation data is attached to the graph.
        batch_size: Number of rows to commit per batch.

    Returns:
        Dict with counts: {"nodes": int, "edges": int, "skipped_edges": int}
    """
    logger.info("Clearing existing edges for subregion '%s'...", subregion)
    db.query(Edge).filter(Edge.subregion == subregion).delete()
    db.commit()

    # Delete orphaned nodes — nodes no longer referenced by any edge in any subregion.
    # This correctly handles border nodes shared between subregions: they stay in the DB
    # as long as at least one subregion's edges still reference them.
    orphan_result = db.execute(text("""
        DELETE FROM graph_nodes
        WHERE id NOT IN (
            SELECT source_node FROM graph_edges
            UNION
            SELECT target_node FROM graph_edges
        )
    """))
    db.commit()
    logger.info("Deleted %d orphaned nodes.", orphan_result.rowcount)

    # --- Nodes — use INSERT ... ON CONFLICT DO NOTHING ---
    # Border nodes shared by multiple subregion bounding boxes will already exist;
    # we skip re-inserting them rather than raising a UniqueViolation.
    logger.info("Storing %d nodes (ON CONFLICT DO NOTHING for shared border nodes)...", len(G.nodes))
    node_batch: list[dict] = []

    for osm_id, data in G.nodes(data=True):
        x = data.get("x")
        y = data.get("y")
        if x is None or y is None:
            continue
        elevation = data.get("elevation") if has_elevation else None
        node_batch.append({
            "id": int(osm_id),
            "geom": from_shape(Point(x, y), srid=4326),
            "elevation_m": elevation,
            "subregion": subregion,
        })
        if len(node_batch) >= batch_size:
            db.execute(pg_insert(Node).values(node_batch).on_conflict_do_nothing(index_elements=["id"]))
            db.commit()
            node_batch = []

    if node_batch:
        db.execute(pg_insert(Node).values(node_batch).on_conflict_do_nothing(index_elements=["id"]))
        db.commit()
    logger.info("Nodes stored.")

    # --- Edges ---
    total_edges = len(G.edges)
    logger.info("Storing %d edges with enrichment...", total_edges)

    edge_batch = []
    skipped = 0
    stored = 0

    for u, v, key, data in G.edges(data=True, keys=True):
        # Skip edges for nodes we didn't store
        if u not in G.nodes or v not in G.nodes:
            skipped += 1
            continue

        tags = {k: v_val for k, v_val in data.items() if isinstance(v_val, (str, int, float, bool))}

        enriched = enrich_edge(tags, has_elevation=has_elevation)

        # Skip edges bikes can't use
        if not enriched["bike_access"]:
            skipped += 1
            continue

        geom = _get_edge_geometry(G, u, v, data)
        climb_up, climb_down = _compute_climb(G, u, v, data, has_elevation)
        distance_m = float(data.get("length", 0.0) or 0.0)

        edge_batch.append(Edge(
            source_node=int(u),
            target_node=int(v),
            geom=from_shape(geom, srid=4326),
            distance_m=distance_m,
            climb_up_m=float(climb_up),
            climb_down_m=float(climb_down),
            road_class=enriched["road_class"],
            bike_access=enriched["bike_access"],
            is_oneway=enriched["is_oneway"],
            surface_class=enriched["surface_class"],
            surface_confidence=enriched["surface_confidence"],
            hike_a_bike_risk=enriched["hike_a_bike_risk"],
            rideability_score=enriched["rideability_score"],
            traffic_score=enriched["traffic_score"],
            technicality_score=enriched["technicality_score"],
            scenic_score=enriched["scenic_score"],
            data_quality_score=enriched["data_quality_score"],
            subregion=subregion,
        ))
        stored += 1

        if len(edge_batch) >= batch_size:
            db.bulk_save_objects(edge_batch)
            db.commit()
            edge_batch = []
            logger.info("  ... %d / %d edges stored", stored, total_edges)

    if edge_batch:
        db.bulk_save_objects(edge_batch)
        db.commit()

    logger.info(
        "Graph stored: %d nodes, %d edges (%d skipped — no bike access or missing geometry).",
        len(G.nodes), stored, skipped,
    )
    return {"nodes": len(G.nodes), "edges": stored, "skipped_edges": skipped}


def ingest_subregion(
    subregion: str,
    db: Session,
    raster_path: Optional[str] = None,
) -> dict:
    """
    Full ingest pipeline for one subregion: download → elevation → store.

    Args:
        subregion: One of "marin", "point_reyes", "sonoma_south".
        db: SQLAlchemy session.
        raster_path: Optional path to SRTM raster for elevation.
                     If None, falls back to SRTM_RASTER_PATH from .env.

    Returns:
        Stats dict from store_graph.
    """
    if raster_path is None and settings.srtm_raster_path:
        raster_path = settings.srtm_raster_path
        logger.info("Using SRTM raster from config: %s", raster_path)

    G = download_graph(subregion)
    has_elevation = attach_elevation(G, raster_path)
    stats = store_graph(G, subregion, db, has_elevation=has_elevation)

    # Flush the in-memory routing cache so the next planning call reloads from DB
    try:
        from backend.modules.planner.leg_generator import invalidate_graph_cache
        invalidate_graph_cache(subregion)
        logger.info("Graph cache invalidated for '%s'.", subregion)
    except ImportError:
        pass

    logger.info(
        "Ingest complete for '%s': %d nodes, %d edges.",
        subregion, stats["nodes"], stats["edges"],
    )
    return stats
