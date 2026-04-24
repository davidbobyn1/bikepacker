"""
Soft scorer — Phase 9.

Scores assembled trips across 11 dimensions, each in [0.0, 1.0].
Weights are rider-profile-aware — an elite rider weights climbing
differently than a beginner.

Dimensions:
    1.  distance_fit
    2.  daily_effort_fit
    3.  climbing_fit
    4.  surface_fit
    5.  rider_fit
    6.  overnight_quality
    7.  logistics_fit
    8.  traffic_comfort
    9.  scenic_value
    10. uncertainty_confidence
    11. loop_quality
"""

import logging
import math
from dataclasses import dataclass

from backend.modules.planner.trip_assembler import AssembledTrip
from backend.schemas.trip_spec import TripSpec
from backend.schemas.route import ScoreBreakdown

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rider-aware weights per fitness level
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, dict[str, float]] = {
    "beginner": {
        "distance_fit":        0.12,
        "daily_effort_fit":    0.15,
        "climbing_fit":        0.15,
        "surface_fit":         0.10,
        "rider_fit":           0.12,
        "overnight_quality":   0.12,
        "logistics_fit":       0.08,
        "traffic_comfort":     0.06,
        "scenic_value":        0.04,
        "uncertainty_confidence": 0.04,
        "loop_quality":        0.02,
    },
    "intermediate": {
        "distance_fit":        0.10,
        "daily_effort_fit":    0.12,
        "climbing_fit":        0.10,
        "surface_fit":         0.12,
        "rider_fit":           0.10,
        "overnight_quality":   0.12,
        "logistics_fit":       0.08,
        "traffic_comfort":     0.08,
        "scenic_value":        0.08,
        "uncertainty_confidence": 0.06,
        "loop_quality":        0.04,
    },
    "strong": {
        "distance_fit":        0.10,
        "daily_effort_fit":    0.10,
        "climbing_fit":        0.08,
        "surface_fit":         0.14,
        "rider_fit":           0.08,
        "overnight_quality":   0.10,
        "logistics_fit":       0.06,
        "traffic_comfort":     0.10,
        "scenic_value":        0.12,
        "uncertainty_confidence": 0.08,
        "loop_quality":        0.04,
    },
    "elite": {
        "distance_fit":        0.08,
        "daily_effort_fit":    0.08,
        "climbing_fit":        0.06,
        "surface_fit":         0.14,
        "rider_fit":           0.06,
        "overnight_quality":   0.08,
        "logistics_fit":       0.04,
        "traffic_comfort":     0.12,
        "scenic_value":        0.16,
        "uncertainty_confidence": 0.10,
        "loop_quality":        0.08,
    },
}


def _bell(value: float, target: float, tolerance: float) -> float:
    """Gaussian-shaped fit score: 1.0 at target, decays with distance."""
    if tolerance <= 0:
        return 1.0 if abs(value - target) < 0.001 else 0.0
    return math.exp(-0.5 * ((value - target) / tolerance) ** 2)


def score_distance_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """How well total distance matches the target band."""
    mid = (spec.total_distance_km.min + spec.total_distance_km.max) / 2
    tolerance = (spec.total_distance_km.max - spec.total_distance_km.min) / 2
    return round(_bell(trip.metrics.total_distance_km, mid, max(tolerance, 10)), 3)


def score_daily_effort_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """How evenly distributed are the per-day distances vs rider comfort."""
    comfort = spec.rider_profile.comfort_daily_km
    scores = []
    for day_dist in trip.metrics.per_day_distance_km:
        scores.append(_bell(day_dist, comfort, comfort * 0.30))
    return round(sum(scores) / max(len(scores), 1), 3)


def score_climbing_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """How well total climbing matches rider capacity."""
    days = trip.trip_days
    capacity = spec.rider_profile.comfort_daily_climbing_m * days
    actual = trip.metrics.total_climbing_m
    # If no elevation data, return neutral score
    if actual == 0:
        return 0.5
    return round(_bell(actual, capacity * 0.75, capacity * 0.35), 3)


def score_surface_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """How close is gravel ratio to the target."""
    target = spec.surface_target.gravel_ratio
    tolerance = spec.surface_target.tolerance
    return round(_bell(trip.metrics.gravel_ratio, target, max(tolerance, 0.05)), 3)


def score_rider_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """How well technicality matches rider skill."""
    skill = spec.rider_profile.technical_skill
    tech = trip.metrics.__dict__.get("technicality_avg", 0.2)

    # Per skill level, what technicality range is comfortable?
    target = {"low": 0.15, "medium": 0.35, "high": 0.60}.get(skill, 0.35)
    return round(_bell(tech, target, 0.20), 3)


def score_overnight_quality(trip: AssembledTrip, spec: TripSpec) -> float:
    """Average overnight confidence weighted by tier."""
    options = trip.overnight_options
    if not options:
        return 0.0
    tier_scores = {1: 1.0, 2: 0.65, 3: 0.35}
    scores = [o.confidence_score * tier_scores.get(o.tier, 0.3) for o in options]
    return round(sum(scores) / len(scores), 3)


def score_logistics_fit(trip: AssembledTrip, spec: TripSpec) -> float:
    """
    Score logistics coverage based on proximity to grocery and water POIs.

    Uses grocery_avg_km and water_avg_km populated by enrich_trip_logistics().
    Falls back to neutral 0.5 if not yet enriched.

    Scoring:
        grocery: 1.0 if <=5 km, 0.5 at 20 km, 0.0 at 50 km
        water:   1.0 if <=2 km, 0.5 at 10 km, 0.0 at 30 km
        combined: weighted average (grocery 0.5 + water 0.5)
        If grocery not required: water weighted 0.7, grocery 0.3
    """
    NO_POI = 50.0

    grocery_km = trip.metrics.grocery_avg_km
    water_km = trip.metrics.water_avg_km

    if grocery_km is None and water_km is None:
        return 0.5  # not enriched — neutral

    def _proximity_score(km: float, good_km: float, ok_km: float, bad_km: float) -> float:
        if km <= good_km:
            return 1.0
        if km >= bad_km:
            return 0.0
        if km <= ok_km:
            return 0.5 + 0.5 * (ok_km - km) / (ok_km - good_km)
        return 0.5 * (bad_km - km) / (bad_km - ok_km)

    grocery_score = _proximity_score(grocery_km or NO_POI, 5.0, 20.0, 50.0)
    water_score   = _proximity_score(water_km  or NO_POI, 2.0, 10.0, 30.0)

    grocery_required = spec.logistics_preferences.grocery_access_required
    water_required   = spec.logistics_preferences.water_access_required

    if grocery_required and water_required:
        combined = grocery_score * 0.5 + water_score * 0.5
    elif water_required:
        combined = grocery_score * 0.3 + water_score * 0.7
    elif grocery_required:
        combined = grocery_score * 0.7 + water_score * 0.3
    else:
        combined = grocery_score * 0.4 + water_score * 0.6  # water slightly more important

    return round(combined, 3)


def score_traffic_comfort(trip: AssembledTrip, spec: TripSpec) -> float:
    """Average traffic score across all legs."""
    return round(trip.metrics.traffic_avg, 3)


def score_scenic_value(trip: AssembledTrip, spec: TripSpec) -> float:
    """Coverage-weighted scenic score."""
    # Weight by uncertain_km — less uncertain = more reliable scenic signal
    total_dist = max(trip.metrics.total_distance_km, 0.1)
    uncertain_ratio = trip.metrics.uncertain_km / total_dist
    coverage_weight = 0.5 + 0.5 * (1.0 - min(uncertain_ratio, 1.0))
    raw = trip.metrics.scenic_avg
    return round(raw * coverage_weight, 3)


def score_uncertainty_confidence(trip: AssembledTrip, spec: TripSpec) -> float:
    """Penalise routes with high uncertain surface coverage."""
    total_dist = max(trip.metrics.total_distance_km, 0.1)
    uncertain_ratio = trip.metrics.uncertain_km / total_dist
    return round(max(1.0 - uncertain_ratio * 2.0, 0.0), 3)


def score_loop_quality(trip: AssembledTrip, spec: TripSpec) -> float:
    """Reward clean loops, penalise closure gaps and edge overlap."""
    # Tighter scale: 6 km gap → full penalty (was 10 km)
    closure_penalty = min(trip.metrics.loop_closure_km / 6.0, 1.0)
    # Steeper overlap penalty: sqrt amplifies mid-range overlap (e.g. 25% overlap → 0.5 penalty)
    overlap_penalty = math.sqrt(trip.metrics.duplicate_ratio)
    return round(max(1.0 - closure_penalty - overlap_penalty, 0.0), 3)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

SCORERS = {
    "distance_fit":           score_distance_fit,
    "daily_effort_fit":       score_daily_effort_fit,
    "climbing_fit":           score_climbing_fit,
    "surface_fit":            score_surface_fit,
    "rider_fit":              score_rider_fit,
    "overnight_quality":      score_overnight_quality,
    "logistics_fit":          score_logistics_fit,
    "traffic_comfort":        score_traffic_comfort,
    "scenic_value":           score_scenic_value,
    "uncertainty_confidence": score_uncertainty_confidence,
    "loop_quality":           score_loop_quality,
}


def score_trip(trip: AssembledTrip, spec: TripSpec) -> ScoreBreakdown:
    """
    Compute all 11 soft scores and weighted total for a trip.

    Args:
        trip: Assembled trip candidate.
        spec: TripSpec with rider profile and preferences.

    Returns:
        ScoreBreakdown with per-dimension scores and weighted_total.
    """
    fitness = spec.rider_profile.fitness_level
    weights = WEIGHTS.get(fitness, WEIGHTS["intermediate"])

    scores: dict[str, float] = {}
    for dim, fn in SCORERS.items():
        scores[dim] = fn(trip, spec)

    weighted_total = sum(scores[dim] * weights[dim] for dim in scores)
    weighted_total = round(min(max(weighted_total, 0.0), 1.0), 4)

    logger.info(
        "Scores [%s]: dist=%.2f effort=%.2f climb=%.2f surface=%.2f rider=%.2f "
        "overnight=%.2f traffic=%.2f scenic=%.2f uncertainty=%.2f loop=%.2f -> total=%.3f",
        fitness,
        scores["distance_fit"], scores["daily_effort_fit"], scores["climbing_fit"],
        scores["surface_fit"], scores["rider_fit"], scores["overnight_quality"],
        scores["traffic_comfort"], scores["scenic_value"],
        scores["uncertainty_confidence"], scores["loop_quality"],
        weighted_total,
    )

    return ScoreBreakdown(
        **scores,
        weighted_total=weighted_total,
    )


def rank_trips(
    trips: list[AssembledTrip],
    spec: TripSpec,
) -> list[tuple[AssembledTrip, ScoreBreakdown]]:
    """
    Score and rank all valid trips, returning top results sorted by score.

    Args:
        trips: List of assembled trips (mix of valid/invalid).
        spec: TripSpec.

    Returns:
        List of (trip, score) tuples, sorted by weighted_total descending.
        Only valid trips are included.
    """
    from backend.modules.scoring.hard_filters import apply_hard_filters

    results = []
    for trip in trips:
        failures = apply_hard_filters(trip, spec)
        if failures:
            trip.rejection_reason = "; ".join(failures)
            continue
        score = score_trip(trip, spec)
        results.append((trip, score))

    results.sort(key=lambda x: x[1].weighted_total, reverse=True)
    logger.info("Ranked %d valid trips (of %d total)", len(results), len(trips))
    return results
