"""
Hard filters — Phase 8.

Binary pass/fail checks applied before soft scoring.
A trip that fails any hard filter is rejected outright.
All failures are recorded so the relaxation engine knows what to loosen.
"""

import logging
from backend.modules.planner.trip_assembler import AssembledTrip
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)

# Maximum loop closure gap before rejecting as non-loop
MAX_LOOP_CLOSURE_KM = 5.0

# Maximum fraction of total distance that can be hike-a-bike
MAX_HAB_RATIO = 0.20


def apply_hard_filters(trip: AssembledTrip, spec: TripSpec) -> list[str]:
    """
    Apply all hard filters to a trip candidate.

    Args:
        trip: Assembled trip to evaluate.
        spec: TripSpec with rider constraints.

    Returns:
        List of failure reason strings. Empty = passed all filters.
    """
    failures = []
    m = trip.metrics
    rider = spec.rider_profile

    # 1. Must have a valid overnight plan
    if not trip.overnight_options:
        failures.append("no_overnight_plan")

    # 2. Loop closure — if loop is preferred/required
    if spec.route_shape.preferred == "loop":
        if m.loop_closure_km > MAX_LOOP_CLOSURE_KM:
            failures.append(f"loop_closure_{m.loop_closure_km:.1f}km_exceeds_{MAX_LOOP_CLOSURE_KM}km")

    # 3. Total distance bounds
    dist = m.total_distance_km
    if dist < spec.total_distance_km.min * 0.60:
        failures.append(f"too_short_{dist:.1f}km_min_{spec.total_distance_km.min}km")
    if dist > spec.total_distance_km.max * 1.40:
        failures.append(f"too_long_{dist:.1f}km_max_{spec.total_distance_km.max}km")

    # 4. Per-day effort — no single day should wildly exceed rider hard max
    hard_max_km = rider.comfort_daily_km * 1.60
    for i, day_dist in enumerate(m.per_day_distance_km):
        if day_dist > hard_max_km:
            failures.append(f"day_{i+1}_effort_{day_dist:.1f}km_exceeds_hard_max_{hard_max_km:.1f}km")

    # 5. Hike-a-bike ratio
    if m.total_distance_km > 0:
        hab_ratio = m.hike_a_bike_km / m.total_distance_km
        if hab_ratio > MAX_HAB_RATIO:
            failures.append(f"hike_a_bike_ratio_{hab_ratio:.2f}_exceeds_{MAX_HAB_RATIO}")

    # 6. Overnight confidence — camping required but no tier-1/2 options
    if spec.overnight.camping_required:
        overnights = trip.overnight_options
        if overnights and all(o.tier >= 3 for o in overnights):
            if rider.remote_tolerance == "low":
                failures.append("all_overnights_tier3_remote_tolerance_low")

    if failures:
        logger.info("Trip failed hard filters: %s", failures)
    else:
        logger.debug("Trip passed all hard filters")

    return failures
