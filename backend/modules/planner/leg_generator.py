"""
Leg generator — Phase 6.

Given an origin point and a destination (overnight anchor), generates
3–4 candidate route variants using NetworkX on the enriched graph.

Weight functions produce different character routes:
  - shortest:      minimise distance
  - lowest_climb:  avoid elevation gain
  - most_unpaved:  maximise gravel/dirt surface
  - least_traffic: avoid busy roads

The graph is loaded from PostGIS once per subregion and cached in memory.
Multiple subregions can be merged into a supergraph for cross-region routing.
"""

import hashlib
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Edge, Node

logger = logging.getLogger(__name__)

# Module-level graph cache.
# Keys are either a single subregion name ("marin") or a sorted pipe-joined
# composite key for merged graphs ("marin|point_reyes").
_graph_cache: dict[str, nx.DiGraph] = {}


def invalidate_graph_cache(subregion: str | None = None) -> None:
    """
    Clear the in-memory graph cache.

    Pass subregion=None to clear everything.
    Pass a subregion name to clear that subregion's individual entry AND any
    composite (merged) cache entries that include it.
    """
    if subregion is None:
        _graph_cache.clear()
    else:
        keys_to_drop = [k for k in _graph_cache if subregion in k.split("|")]
        for k in keys_to_drop:
            _graph_cache.pop(k, None)


@dataclass
class LegMetrics:
    """Computed metrics for one route leg."""
    distance_km: float
    climb_up_m: float
    climb_down_m: float
    gravel_ratio: float        # fraction of distance that is gravel/dirt
    paved_ratio: float
    uncertain_km: float        # distance on edges with surface_confidence < 0.4
    hike_a_bike_km: float      # distance on high hike-a-bike-risk edges
    technicality_avg: float
    traffic_avg: float
    scenic_avg: float
    node_count: int


@dataclass
class LegVariant:
    """One candidate route between two points."""
    weight_fn: str                        # "shortest" | "lowest_climb" | "most_unpaved" | "least_traffic"
    node_ids: list[int] = field(default_factory=list)
    geometry_coords: list[tuple[float, float]] = field(default_factory=list)  # (lon, lat) pairs
    metrics: Optional[LegMetrics] = None
    rejection_reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.rejection_reason is None

    @property
    def fingerprint(self) -> str:
        """Hash of node sequence — used to deduplicate identical routes."""
        key = ",".join(str(n) for n in self.node_ids)
        return hashlib.md5(key.encode()).hexdigest()[:12]


def load_graph(subregion: str, db: Session) -> nx.DiGraph:
    """
    Load enriched graph for a subregion from PostGIS into a NetworkX DiGraph.
    Result is cached in memory — subsequent calls return the cached graph.

    Args:
        subregion: e.g. "marin"
        db: SQLAlchemy session (only used on first load).

    Returns:
        Enriched nx.DiGraph ready for weighted shortest-path.
    """
    if subregion in _graph_cache:
        logger.debug("Graph cache hit for '%s'", subregion)
        return _graph_cache[subregion]

    logger.info("Loading graph for '%s' from PostGIS...", subregion)

    G = nx.DiGraph()

    # Load edges first — we'll derive which nodes to load from the edge endpoints.
    # (Filtering nodes by subregion is wrong: border nodes shared between two
    # subregions are stored under whichever subregion ingested them first.)
    edges = db.execute(
        select(
            Edge.source_node, Edge.target_node, Edge.geom,
            Edge.distance_m, Edge.climb_up_m, Edge.climb_down_m,
            Edge.surface_class, Edge.surface_confidence,
            Edge.bike_access, Edge.is_oneway,
            Edge.rideability_score, Edge.traffic_score,
            Edge.technicality_score, Edge.scenic_score,
            Edge.hike_a_bike_risk, Edge.data_quality_score,
            Edge.rwgps_confidence_boost,
        ).where(Edge.subregion == subregion, Edge.bike_access == True)
    ).all()

    # Collect all node IDs referenced by these edges, then load those nodes.
    edge_list = list(edges)
    edge_node_ids = set()
    for row in edge_list:
        edge_node_ids.add(row.source_node)
        edge_node_ids.add(row.target_node)

    from geoalchemy2.shape import to_shape
    if edge_node_ids:
        node_rows = db.execute(
            select(Node.id, Node.geom).where(Node.id.in_(list(edge_node_ids)))
        ).all()
        for node_id, geom in node_rows:
            pt = to_shape(geom)
            G.add_node(node_id, x=pt.x, y=pt.y)

    logger.info("  Loaded %d nodes", G.number_of_nodes())

    for row in edge_list:
        # Extract full road geometry so tracks follow actual roads, not straight
        # lines between intersection nodes.
        geom_coords: Optional[list[tuple[float, float]]] = None
        if row.geom is not None:
            try:
                shape = to_shape(row.geom)
                geom_coords = list(shape.coords)  # (lon, lat) tuples
            except Exception:
                geom_coords = None

        attrs = {
            "_geom_coords":           geom_coords,
            "distance_m":             float(row.distance_m or 0),
            "climb_up_m":             float(row.climb_up_m or 0),
            "climb_down_m":           float(row.climb_down_m or 0),
            "surface_class":          row.surface_class or "unknown",
            "surface_confidence":     float(row.surface_confidence or 0.15),
            "traffic_score":          float(row.traffic_score or 0.5),
            "technicality_score":     float(row.technicality_score or 0.2),
            "scenic_score":           float(row.scenic_score or 0.4),
            "hike_a_bike_risk":       float(row.hike_a_bike_risk or 0.05),
            "rwgps_confidence_boost": float(row.rwgps_confidence_boost or 0.0),
        }
        G.add_edge(row.source_node, row.target_node, **attrs)
        if not row.is_oneway:
            reverse = dict(attrs)
            reverse["climb_up_m"], reverse["climb_down_m"] = attrs["climb_down_m"], attrs["climb_up_m"]
            # Reverse edge stores coords in reverse order so _extract_coords
            # can always read them in traversal direction.
            if geom_coords:
                reverse["_geom_coords"] = list(reversed(geom_coords))
            G.add_edge(row.target_node, row.source_node, **reverse)

    logger.info("  Loaded %d edges (bike-accessible only)", G.number_of_edges())

    # Keep only the largest weakly connected component so snapping never
    # lands on an isolated node with no path to anything else.
    components = list(nx.weakly_connected_components(G))
    largest = max(components, key=len)
    if len(largest) < G.number_of_nodes():
        removed = G.number_of_nodes() - len(largest)
        G = G.subgraph(largest).copy()
        logger.info("  Pruned %d isolated nodes — using largest component (%d nodes)", removed, G.number_of_nodes())

    _graph_cache[subregion] = G
    return G


def load_merged_graph(subregions: list[str], db: Session) -> nx.DiGraph:
    """
    Return a merged DiGraph covering all requested subregions.

    OSM node IDs are globally unique integers, so graphs from adjacent subregions
    share border nodes by ID — nx.compose_all() merges them correctly with no
    duplicates. The merged graph is cached under a sorted pipe-joined key so
    repeated calls with the same subregion set are instant.

    Args:
        subregions: List of subregion names, e.g. ["marin", "point_reyes"].
        db: SQLAlchemy session (only used on cache miss for individual subregions).

    Returns:
        Merged nx.DiGraph containing all edges from every requested subregion.
    """
    if not subregions:
        raise ValueError("subregions list must not be empty")

    # Normalise to a stable cache key
    cache_key = "|".join(sorted(set(subregions)))

    if cache_key in _graph_cache:
        logger.debug("Merged graph cache hit for '%s'", cache_key)
        return _graph_cache[cache_key]

    # Load (or retrieve from cache) each individual subregion graph
    graphs = [load_graph(s, db) for s in sorted(set(subregions))]

    if len(graphs) == 1:
        # No merge needed — just alias to the single graph
        _graph_cache[cache_key] = graphs[0]
        return graphs[0]

    logger.info("Merging graphs for subregions: %s", cache_key)
    merged = nx.compose_all(graphs)

    # Do NOT re-apply largest-component pruning here. Each individual subregion
    # graph was already pruned before caching. Adjacent subregions may not share
    # direct road connections (e.g. Marin and Point Reyes have non-overlapping
    # bounding boxes). Pruning to the largest component would silently drop entire
    # subregion graphs. Instead, let nx.shortest_path raise NetworkXNoPath for
    # legs that span truly disconnected regions — that is handled upstream.
    logger.info(
        "  Merged graph: %d nodes, %d edges",
        merged.number_of_nodes(), merged.number_of_edges(),
    )

    _graph_cache[cache_key] = merged
    return merged


def _nearest_node(G: nx.DiGraph, lat: float, lon: float) -> int:
    """Return the node ID nearest to (lat, lon) using Euclidean distance."""
    best_id = None
    best_dist = float("inf")
    for node_id, data in G.nodes(data=True):
        dx = data["x"] - lon
        dy = data["y"] - lat
        d = dx * dx + dy * dy
        if d < best_dist:
            best_dist = d
            best_id = node_id
    return best_id


def _weight_shortest(u, v, data) -> float:
    return data.get("distance_m", 1.0)


def _weight_lowest_climb(u, v, data) -> float:
    d = data.get("distance_m", 1.0)
    climb = data.get("climb_up_m", 0.0)
    return d + climb * 10.0


def _weight_most_unpaved(u, v, data) -> float:
    d = data.get("distance_m", 1.0)
    surface = data.get("surface_class", "unknown")
    if surface == "paved":
        base = d * 2.0
    elif surface == "unknown":
        base = d * 1.3
    else:
        base = d * 0.8  # reward gravel/dirt
    # Popular cycling edges (from RideWithGPS traces) get a cost reduction.
    # Max boost 0.40 → 16% cheaper. To disable: remove this line.
    boost = data.get("rwgps_confidence_boost", 0.0)
    return base * (1.0 - boost * 0.4)


def _weight_least_traffic(u, v, data) -> float:
    d = data.get("distance_m", 1.0)
    traffic = max(data.get("traffic_score", 0.5), 0.01)
    return d / traffic


WEIGHT_FUNCTIONS = {
    "shortest":      _weight_shortest,
    "lowest_climb":  _weight_lowest_climb,
    "most_unpaved":  _weight_most_unpaved,
    "least_traffic": _weight_least_traffic,
}

# Hike-a-bike tolerance per rider skill level
HIKE_A_BIKE_LIMITS = {
    "low":    0.25,
    "medium": 0.55,
    "high":   0.80,
}


def _compute_metrics(G: nx.DiGraph, node_ids: list[int]) -> LegMetrics:
    """Compute LegMetrics by walking the edge sequence."""
    total_dist = 0.0
    climb_up = 0.0
    climb_down = 0.0
    gravel_dist = 0.0
    paved_dist = 0.0
    uncertain_dist = 0.0
    hike_a_bike_dist = 0.0
    tech_sum = 0.0
    traffic_sum = 0.0
    scenic_sum = 0.0
    edge_count = 0

    for u, v in zip(node_ids, node_ids[1:]):
        data = G.get_edge_data(u, v)
        if not data:
            continue
        d = data.get("distance_m", 0.0)
        total_dist += d
        climb_up += data.get("climb_up_m", 0.0)
        climb_down += data.get("climb_down_m", 0.0)

        surface = data.get("surface_class", "unknown")
        conf = data.get("surface_confidence", 0.15)

        if surface == "paved":
            paved_dist += d
        elif surface in ("gravel", "dirt"):
            gravel_dist += d

        if conf < 0.4:
            uncertain_dist += d

        if data.get("hike_a_bike_risk", 0) > 0.5:
            hike_a_bike_dist += d

        tech_sum += data.get("technicality_score", 0.2)
        traffic_sum += data.get("traffic_score", 0.5)
        scenic_sum += data.get("scenic_score", 0.4)
        edge_count += 1

    ec = max(edge_count, 1)
    return LegMetrics(
        distance_km=round(total_dist / 1000, 2),
        climb_up_m=round(climb_up, 1),
        climb_down_m=round(climb_down, 1),
        gravel_ratio=round(gravel_dist / max(total_dist, 1), 3),
        paved_ratio=round(paved_dist / max(total_dist, 1), 3),
        uncertain_km=round(uncertain_dist / 1000, 2),
        hike_a_bike_km=round(hike_a_bike_dist / 1000, 2),
        technicality_avg=round(tech_sum / ec, 3),
        traffic_avg=round(traffic_sum / ec, 3),
        scenic_avg=round(scenic_sum / ec, 3),
        node_count=len(node_ids),
    )


def _extract_coords(G: nx.DiGraph, node_ids: list[int]) -> list[tuple[float, float]]:
    """
    Return (lon, lat) coordinate list by stitching per-edge road geometries.

    For each consecutive edge (u, v), uses the _geom_coords stored on that edge
    (extracted from the PostGIS LineString at graph load time). Falls back to
    node (x, y) positions when geometry is absent. Reverse edges already have
    their coords stored in reversed order, so traversal direction is always correct.
    """
    if not node_ids:
        return []

    coords: list[tuple[float, float]] = []
    for i, (u, v) in enumerate(zip(node_ids[:-1], node_ids[1:])):
        edge = G.get_edge_data(u, v)
        geom = edge.get("_geom_coords") if edge else None
        if geom:
            if i == 0:
                coords.extend(geom)
            else:
                coords.extend(geom[1:])  # skip first — duplicate of previous tail
        else:
            # No geometry: fall back to node coords
            if i == 0:
                nd = G.nodes[u]
                coords.append((nd["x"], nd["y"]))
            nd = G.nodes[v]
            coords.append((nd["x"], nd["y"]))

    return coords


def _path_distance_km(G: nx.DiGraph, node_ids: list[int]) -> float:
    """Sum edge distances along a node sequence, in km."""
    return sum(
        G.get_edge_data(u, v, {}).get("distance_m", 0)
        for u, v in zip(node_ids, node_ids[1:])
    ) / 1000.0


def _insert_via_point(
    G: nx.DiGraph,
    origin_node: int,
    dest_node: int,
    direct_path: list[int],
    direct_km: float,
    target_km: float,
    weight_fn,
) -> list[int]:
    """
    Temporary route-lengthening heuristic for the campsite-first planning model.

    When the direct route from origin to destination is much shorter than the
    requested daily distance (< 65% of target), inserts a via-point in the
    direction away from the destination to force a longer, more interesting
    route before arriving at the overnight stop.

    NOTE: This is intentionally isolated from core planner logic. It is a
    tactical fix for the current campsite-first model in areas where campsites
    cluster close to the origin (e.g. Marin). A future corridor-first v2
    approach should supersede this entirely.

    Args:
        G: Routing graph.
        origin_node: Start node ID.
        dest_node: Destination (overnight anchor) node ID.
        direct_path: Pre-computed direct path (used as fallback).
        direct_km: Distance of direct_path in km.
        target_km: Desired leg length in km (typically spec daily comfort).
        weight_fn: Weight function for sub-routing calls.

    Returns:
        Extended path [origin -> via -> dest], or direct_path if no suitable
        via-point is found or routing through it fails.
    """
    pad_m = (target_km - direct_km) * 500.0   # half the shortfall, in metres
    if pad_m <= 100:
        return direct_path

    ox = G.nodes[origin_node]["x"]
    oy = G.nodes[origin_node]["y"]
    dx = G.nodes[dest_node]["x"]
    dy = G.nodes[dest_node]["y"]

    # Half-plane away from destination
    angle_to_dest = math.atan2(dy - oy, dx - ox)
    angle_away = angle_to_dest + math.pi

    deg_per_m = 1.0 / 111_000.0
    lo = pad_m * 0.5 * deg_per_m
    hi = pad_m * 1.8 * deg_per_m

    # Sample up to 500 nodes for performance (full scan is O(N) per call)
    all_nodes = list(G.nodes(data=True))
    sample = random.sample(all_nodes, min(500, len(all_nodes)))

    candidates: list[tuple[int, float]] = []
    for nid, ndata in sample:
        if nid in (origin_node, dest_node):
            continue
        nx_ = ndata["x"]
        ny_ = ndata["y"]
        d = math.hypot(nx_ - ox, ny_ - oy)
        if not (lo <= d <= hi):
            continue
        angle = math.atan2(ny_ - oy, nx_ - ox)
        angle_diff = abs((angle - angle_away + math.pi) % (2 * math.pi) - math.pi)
        if angle_diff > math.pi / 2:   # must be in away half-plane
            continue
        # Score candidate by the scenic quality of its outgoing edges
        scenic = max(
            (G.get_edge_data(nid, nb, {}).get("scenic_score", 0.0)
             for nb in list(G.successors(nid))[:5]),
            default=0.0,
        )
        candidates.append((nid, scenic))

    if not candidates:
        logger.debug("via-point: no candidates in away half-plane, using direct")
        return direct_path

    via_node = max(candidates, key=lambda c: c[1])[0]

    try:
        path1 = nx.shortest_path(G, origin_node, via_node, weight=weight_fn)
        path2 = nx.shortest_path(G, via_node, dest_node, weight=weight_fn)
        extended = path1 + path2[1:]
        logger.debug(
            "via-point: %.1f km -> %.1f km (target %.1f km)",
            direct_km, _path_distance_km(G, extended), target_km,
        )
        return extended
    except nx.NetworkXNoPath:
        logger.debug("via-point: routing through via-node failed, using direct")
        return direct_path


def generate_legs(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    subregions: list[str],
    technical_skill: str,
    db: Session,
    target_daily_km: float = 0.0,
) -> list[LegVariant]:
    """
    Generate 3–4 route variants between origin and destination.

    Args:
        origin_lat / origin_lon: Start point coordinates.
        dest_lat / dest_lon: End point (overnight anchor) coordinates.
        subregions: List of subregion names to route across. Pass more than one
            to enable cross-subregion routing via a merged supergraph.
        technical_skill: "low" | "medium" | "high" — governs hike-a-bike rejection.
        db: SQLAlchemy session.
        target_daily_km: If > 0 and the direct route is < 65% of this value,
            a via-point detour is inserted to produce a longer, more interesting
            leg. See _insert_via_point() for details.

    Returns:
        List of LegVariant objects. Invalid variants include a rejection_reason.
        Deduplicated by node sequence fingerprint.
    """
    G = load_merged_graph(subregions, db)
    graph_label = "|".join(sorted(set(subregions)))

    origin_node = _nearest_node(G, origin_lat, origin_lon)
    dest_node = _nearest_node(G, dest_lat, dest_lon)

    logger.info(
        "Generating legs: origin_node=%d -> dest_node=%d (%s graph, %d nodes)",
        origin_node, dest_node, graph_label, G.number_of_nodes(),
    )

    # Fast connectivity pre-check: if origin and dest are in different weakly connected
    # components, no path exists for any weight function. Bail out immediately rather
    # than running 4 Dijkstra calls that all return NetworkXNoPath.
    if not nx.has_path(G.to_undirected(), origin_node, dest_node):
        logger.warning(
            "  Destination node %d is unreachable from origin %d (disconnected components) — skipping",
            dest_node, origin_node,
        )
        return []

    hab_limit = HIKE_A_BIKE_LIMITS.get(technical_skill, 0.55)
    variants: list[LegVariant] = []
    seen_fingerprints: set[str] = set()
    shortest_dist: Optional[float] = None

    for name, weight_fn in WEIGHT_FUNCTIONS.items():
        variant = LegVariant(weight_fn=name)

        try:
            path = nx.shortest_path(G, origin_node, dest_node, weight=weight_fn)
        except nx.NetworkXNoPath:
            variant.rejection_reason = "no_path"
            logger.warning("  %s: no path found", name)
            variants.append(variant)
            continue
        except nx.NodeNotFound as e:
            variant.rejection_reason = f"node_not_found: {e}"
            variants.append(variant)
            continue

        # Via-point lengthening: if direct route is much shorter than the
        # target daily distance, insert a detour in the direction away from
        # the destination to pad the leg to a more useful length.
        if target_daily_km > 0:
            direct_km = _path_distance_km(G, path)
            if direct_km < target_daily_km * 0.65:
                path = _insert_via_point(
                    G, origin_node, dest_node, path, direct_km, target_daily_km, weight_fn
                )

        variant.node_ids = path
        fp = variant.fingerprint
        if fp in seen_fingerprints:
            logger.debug("  %s: duplicate of existing variant, skipping", name)
            continue
        seen_fingerprints.add(fp)

        metrics = _compute_metrics(G, path)
        variant.metrics = metrics
        variant.geometry_coords = _extract_coords(G, path)

        # Reject: hike-a-bike tolerance exceeded
        if metrics.hike_a_bike_km > 0 and (metrics.hike_a_bike_km / max(metrics.distance_km, 0.1)) > 0.15:
            # Check worst edge directly
            for u, v in zip(path, path[1:]):
                data = G.get_edge_data(u, v) or {}
                if data.get("hike_a_bike_risk", 0) > hab_limit:
                    variant.rejection_reason = f"hike_a_bike_risk_exceeds_{hab_limit}"
                    break

        # Reject: too inefficient vs shortest
        if variant.is_valid:
            if shortest_dist is None:
                shortest_dist = metrics.distance_km
            elif metrics.distance_km > shortest_dist * 1.5:
                variant.rejection_reason = f"too_long_{metrics.distance_km:.1f}km_vs_shortest_{shortest_dist:.1f}km"

        status = "OK" if variant.is_valid else f"REJECTED ({variant.rejection_reason})"
        logger.info(
            "  %s: %.1f km, +%.0f m climb, gravel=%.0f%%, uncertain=%.1f km — %s",
            name, metrics.distance_km, metrics.climb_up_m,
            metrics.gravel_ratio * 100, metrics.uncertain_km, status,
        )
        variants.append(variant)

    valid = [v for v in variants if v.is_valid]
    logger.info("Leg generation complete: %d valid / %d total variants", len(valid), len(variants))
    return variants
