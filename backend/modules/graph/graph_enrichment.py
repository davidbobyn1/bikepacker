"""
Graph enrichment — converts raw OSM edge tags into scored attributes.

All functions are verbatim from docs/enrichment_rules.md.
Run in the exact order defined by enrich_edge().
Do not modify scoring logic without updating enrichment_rules.md first.
"""

ROAD_CLASS_MAP = {
    "cycleway":     "cycleway",
    "path":         "path",
    "footway":      "footway",
    "bridleway":    "bridleway",
    "track":        "track",
    "unclassified": "unclassified",
    "residential":  "residential",
    "service":      "service",
    "tertiary":     "tertiary",
    "secondary":    "secondary",
    "primary":      "primary",
    "trunk":        "trunk",
    "motorway":     "motorway",
}


def compute_road_class(tags: dict) -> str:
    """Map OSM highway tag to normalized road_class string."""
    return ROAD_CLASS_MAP.get(tags.get("highway", "").lower(), "other")


def compute_bike_access(tags: dict) -> bool:
    """
    Determine if a bike can legally and practically travel this edge.
    Returns False for edges that must never appear in any generated route.
    """
    bicycle = tags.get("bicycle", "")
    highway = tags.get("highway", "").lower()
    motor_vehicle = tags.get("motor_vehicle", "")

    # Explicit no
    if bicycle in ("no", "dismount"):
        return False
    if highway in ("motorway", "motorway_link", "trunk", "trunk_link"):
        return False
    if motor_vehicle == "yes" and not bicycle:
        return False

    # Explicit yes
    if bicycle in ("yes", "designated", "permissive", "official"):
        return True
    if highway == "cycleway":
        return True

    # Default by road class
    passable = {
        "path", "track", "bridleway", "unclassified",
        "residential", "service", "tertiary", "secondary"
    }
    return highway in passable


def compute_surface(tags: dict) -> tuple[str, float]:
    """
    Returns (surface_class, surface_confidence).
    surface_class: "paved" | "gravel" | "dirt" | "unknown"
    surface_confidence: 0.0–1.0
    """
    surface = tags.get("surface", "").lower()
    tracktype = tags.get("tracktype", "").lower()
    highway = tags.get("highway", "").lower()
    smoothness = tags.get("smoothness", "").lower()

    # Explicit surface tag present
    if surface in ("asphalt", "paved", "concrete", "compacted_concrete"):
        return "paved", 0.95
    if surface in ("compacted", "fine_gravel", "gravel", "pebblestone", "unpaved", "dirt"):
        return "gravel", 0.90
    if surface in ("ground", "mud", "grass", "sand", "rock", "roots"):
        return "dirt", 0.85

    # No surface tag — infer from highway + tracktype
    if highway == "cycleway":
        return "paved", 0.88
    if highway in ("residential", "unclassified", "service"):
        return "paved", 0.75
    if highway in ("tertiary", "secondary"):
        return "paved", 0.90
    if highway == "track":
        if tracktype in ("grade1", "grade2"):
            return "gravel", 0.70
        if tracktype == "grade3":
            return "dirt", 0.60
        if tracktype in ("grade4", "grade5"):
            return "dirt", 0.55
        return "gravel", 0.40  # track with no tracktype
    if highway in ("path", "footway", "bridleway"):
        if smoothness in ("excellent", "good"):
            return "gravel", 0.55
        return "unknown", 0.20

    return "unknown", 0.15


def compute_hike_a_bike_risk(tags: dict) -> float:
    """
    Returns hike_a_bike_risk in [0.0, 1.0].
    Higher = more likely to require walking the bike.
    """
    sac = tags.get("sac_scale", "").lower()
    highway = tags.get("highway", "").lower()
    tracktype = tags.get("tracktype", "").lower()
    surface = tags.get("surface", "").lower()
    bicycle = tags.get("bicycle", "").lower()

    if sac == "hiking":
        return 0.80
    if sac in ("mountain_hiking", "demanding_mountain_hiking"):
        return 0.95
    if sac == "alpine_hiking":
        return 1.00

    if highway == "track" and tracktype == "grade5":
        return 0.70
    if highway == "track" and tracktype == "grade4":
        return 0.50

    if highway in ("path", "footway") and surface in ("rock", "roots", "grass", "mud"):
        return 0.60
    if highway in ("path", "footway") and surface == "":
        return 0.30

    if highway == "bridleway":
        return 0.20
    if bicycle == "dismount":
        return 0.90

    return 0.05


def compute_rideability(
    tags: dict,
    surface_class: str,
    surface_confidence: float,
    hike_a_bike_risk: float,
) -> float:
    """
    Returns rideability_score in [0.0, 1.0].
    Higher = more rideable for a typical bikepacking rig.
    """
    highway = tags.get("highway", "").lower()

    base = {
        "cycleway":     0.95,
        "residential":  0.88,
        "unclassified": 0.82,
        "tertiary":     0.80,
        "service":      0.75,
        "track":        0.65,
        "bridleway":    0.60,
        "path":         0.50,
        "footway":      0.40,
        "secondary":    0.78,
        "primary":      0.60,
    }.get(highway, 0.50)

    if surface_class == "paved":
        base = min(base + 0.05, 1.0)
    elif surface_class == "dirt":
        base = max(base - 0.15, 0.0)
    elif surface_class == "unknown":
        base = max(base - 0.10, 0.0)

    base *= (0.7 + 0.3 * surface_confidence)
    base *= (1.0 - 0.6 * hike_a_bike_risk)

    return round(max(min(base, 1.0), 0.0), 3)


def compute_traffic_score(tags: dict) -> float:
    """
    Returns traffic_score in [0.0, 1.0].
    Higher = less traffic = better for bikepacking.
    """
    highway = tags.get("highway", "").lower()
    maxspeed = tags.get("maxspeed", "")

    base = {
        "cycleway":     0.95,
        "path":         0.92,
        "track":        0.90,
        "bridleway":    0.90,
        "footway":      0.85,
        "residential":  0.75,
        "unclassified": 0.70,
        "service":      0.65,
        "tertiary":     0.55,
        "secondary":    0.40,
        "primary":      0.20,
        "trunk":        0.05,
        "motorway":     0.00,
    }.get(highway, 0.50)

    try:
        speed_str = str(maxspeed).replace(" mph", "").replace(" km/h", "").replace("mph", "").strip()
        speed = int(speed_str)
        if speed >= 80:
            base = max(base - 0.30, 0.0)
        elif speed >= 50:
            base = max(base - 0.15, 0.0)
    except (ValueError, AttributeError, TypeError):
        pass

    return round(base, 3)


def compute_technicality(
    tags: dict,
    hike_a_bike_risk: float,
    surface_class: str,
) -> float:
    """
    Returns technicality_score in [0.0, 1.0].
    Higher = more technical = requires more skill.
    """
    highway = tags.get("highway", "").lower()
    tracktype = tags.get("tracktype", "").lower()
    mtb_scale = tags.get("mtb:scale", "")

    base = {
        "cycleway":     0.05,
        "residential":  0.05,
        "unclassified": 0.10,
        "track":        0.35,
        "path":         0.50,
        "bridleway":    0.40,
        "footway":      0.55,
    }.get(highway, 0.20)

    if mtb_scale:
        try:
            scale = int(str(mtb_scale).strip()[0])
            base = min(scale / 5.0, 1.0)
        except (ValueError, IndexError):
            pass

    if highway == "track":
        grade_map = {
            "grade1": 0.10, "grade2": 0.25, "grade3": 0.45,
            "grade4": 0.65, "grade5": 0.80,
        }
        base = grade_map.get(tracktype, base)

    if surface_class == "dirt":
        base = min(base + 0.10, 1.0)

    base = min(base + 0.3 * hike_a_bike_risk, 1.0)

    return round(base, 3)


def compute_scenic_score(tags: dict) -> float:
    """
    Returns scenic_score in [0.0, 1.0].
    Low-confidence heuristic — use coverage-weighted averaging at route level.
    """
    highway = tags.get("highway", "").lower()
    name = tags.get("name", "").lower()
    natural = tags.get("natural", "").lower()
    route = tags.get("route", "").lower()

    base = {
        "track":        0.65,
        "path":         0.70,
        "bridleway":    0.68,
        "cycleway":     0.55,
        "unclassified": 0.45,
        "residential":  0.30,
        "tertiary":     0.35,
        "secondary":    0.25,
        "primary":      0.10,
    }.get(highway, 0.40)

    scenic_keywords = (
        "ridge", "coast", "canyon", "creek", "river", "bay",
        "peak", "summit", "loop", "trail", "scenic", "panorama",
    )
    if any(kw in name for kw in scenic_keywords):
        base = min(base + 0.15, 1.0)

    if natural in ("beach", "cliff", "coastline", "ridge", "peak", "wood", "wetland"):
        base = min(base + 0.10, 1.0)

    if route in ("bicycle", "hiking", "foot"):
        base = min(base + 0.10, 1.0)

    return round(base, 3)


def compute_data_quality(
    surface_confidence: float,
    bike_access_explicit: bool,
    has_elevation: bool,
) -> float:
    """
    Returns data_quality_score in [0.0, 1.0].
    Composite signal of how reliable the enriched attributes are.
    """
    score = surface_confidence * 0.5
    score += 0.30 if bike_access_explicit else 0.10
    score += 0.20 if has_elevation else 0.0
    return round(score, 3)


def enrich_edge(tags: dict, has_elevation: bool = False) -> dict:
    """
    Run the full enrichment pipeline for a single edge's OSM tags.
    Returns a dict of all enriched attributes.

    Pipeline order per enrichment_rules.md:
    1. bike_access
    2. surface_class, surface_confidence
    3. hike_a_bike_risk
    4. rideability_score
    5. traffic_score
    6. technicality_score
    7. scenic_score
    8. data_quality_score

    Args:
        tags: Raw OSM tag dict for the edge.
        has_elevation: Whether elevation data is available for this edge's nodes.

    Returns:
        Dict of enriched edge attributes ready to store.
    """
    bike_access = compute_bike_access(tags)
    surface_class, surface_confidence = compute_surface(tags)
    hike_a_bike_risk = compute_hike_a_bike_risk(tags)
    rideability_score = compute_rideability(tags, surface_class, surface_confidence, hike_a_bike_risk)
    traffic_score = compute_traffic_score(tags)
    technicality_score = compute_technicality(tags, hike_a_bike_risk, surface_class)
    scenic_score = compute_scenic_score(tags)

    bike_access_explicit = tags.get("bicycle") is not None
    data_quality_score = compute_data_quality(surface_confidence, bike_access_explicit, has_elevation)

    return {
        "road_class": compute_road_class(tags),
        "bike_access": bike_access,
        "is_oneway": tags.get("oneway") in (True, "yes", "1"),
        "surface_class": surface_class,
        "surface_confidence": surface_confidence,
        "hike_a_bike_risk": hike_a_bike_risk,
        "rideability_score": rideability_score,
        "traffic_score": traffic_score,
        "technicality_score": technicality_score,
        "scenic_score": scenic_score,
        "data_quality_score": data_quality_score,
    }
