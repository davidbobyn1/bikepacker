"""
Relaxation engine — Phase 10.

When the initial planning pass returns fewer than N_MIN valid trips,
this engine applies constraint relaxations in cascade order and re-runs
the pipeline until enough results are found or all steps are exhausted.

Cascade (applied cumulatively in order):
    Step 1: Widen distance band to relax_to bounds
    Step 2: Widen surface tolerance (+0.15, cap 0.40)
    Step 3: Lower overnight tier threshold (remote_tolerance → "medium")
    Step 4: Allow hotel fallback
    Step 5: Allow out-and-back shape
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.modules.planner.anchor_selector import select_anchors
from backend.modules.planner.logistics_enricher import enrich_all_logistics
from backend.modules.planner.trip_assembler import AssembledTrip, assemble_trips
from backend.modules.scoring.soft_scorer import ScoreBreakdown, rank_trips
from backend.schemas.route import RelaxationRecord
from backend.schemas.trip_spec import TripSpec

logger = logging.getLogger(__name__)

N_MIN_RESULTS = 3   # target number of valid trips before stopping
MAX_STEPS = 5       # never apply more than this many relaxation steps


# ---------------------------------------------------------------------------
# Pipeline wrapper
# ---------------------------------------------------------------------------

def _try_pipeline(
    spec: TripSpec,
    db: Session,
) -> list[tuple[AssembledTrip, ScoreBreakdown]]:
    """
    Run anchors → assembly → scoring for the given spec.

    Args:
        spec: TripSpec (possibly relaxed).
        db: SQLAlchemy session.

    Returns:
        Ranked list of (trip, score) tuples that passed all hard filters.
        Empty list if no valid trips found.
    """
    try:
        anchors = select_anchors(spec, db)
        trips = assemble_trips(spec, anchors, db)
        enrich_all_logistics(trips, db)
        return rank_trips(trips, spec)
    except Exception as exc:
        logger.warning("Pipeline error during relaxation step: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Step functions — each returns (new_spec_copy, RelaxationRecord | None)
# None means the step was not applicable / not permitted by policy.
# ---------------------------------------------------------------------------

def _step1_widen_distance(
    spec: TripSpec,
    step: int,
) -> tuple[TripSpec, Optional[RelaxationRecord]]:
    """Widen total_distance_km to relax_to bounds."""
    policy = spec.relaxation_policy
    rt = spec.total_distance_km.relax_to

    if not policy.allow_distance_widen or rt is None:
        return spec, None

    original = {"min": spec.total_distance_km.min, "max": spec.total_distance_km.max}
    relaxed = {"min": rt.min, "max": rt.max}

    if original == relaxed:
        return spec, None

    new_spec = spec.model_copy(deep=True)
    new_spec.total_distance_km.min = rt.min
    new_spec.total_distance_km.max = rt.max

    record = RelaxationRecord(
        step=step,
        dimension="distance",
        original_value=original,
        relaxed_value=relaxed,
        reason=f"No valid trips found; widened distance from {original['min']}-{original['max']} km "
               f"to {relaxed['min']}-{relaxed['max']} km using relax_to bounds",
    )
    return new_spec, record


def _step2_widen_surface(
    spec: TripSpec,
    step: int,
) -> tuple[TripSpec, Optional[RelaxationRecord]]:
    """Widen surface tolerance by 0.15, capped at 0.40."""
    if not spec.relaxation_policy.allow_surface_widen:
        return spec, None

    original = spec.surface_target.tolerance
    relaxed = min(original + 0.15, 0.40)

    if relaxed <= original:
        return spec, None

    new_spec = spec.model_copy(deep=True)
    new_spec.surface_target.tolerance = round(relaxed, 2)

    record = RelaxationRecord(
        step=step,
        dimension="surface_tolerance",
        original_value=original,
        relaxed_value=round(relaxed, 2),
        reason=f"Widened surface tolerance from {original:.2f} to {relaxed:.2f} to accept more route variants",
    )
    return new_spec, record


def _step3_lower_overnight_tier(
    spec: TripSpec,
    step: int,
) -> tuple[TripSpec, Optional[RelaxationRecord]]:
    """Relax overnight tier rejection by upgrading remote_tolerance to 'medium'."""
    if not spec.relaxation_policy.allow_lower_overnight_tier:
        return spec, None

    if spec.rider_profile.remote_tolerance != "low":
        return spec, None

    new_spec = spec.model_copy(deep=True)
    new_spec.rider_profile.remote_tolerance = "medium"

    record = RelaxationRecord(
        step=step,
        dimension="overnight_tier",
        original_value="low",
        relaxed_value="medium",
        reason="Relaxed remote_tolerance from 'low' to 'medium' to allow tier-3 overnights",
    )
    return new_spec, record


def _step4_hotel_fallback(
    spec: TripSpec,
    step: int,
) -> tuple[TripSpec, Optional[RelaxationRecord]]:
    """Enable hotel as a fallback overnight option."""
    if not spec.relaxation_policy.allow_hotel_fallback:
        return spec, None

    if spec.overnight.hotel_allowed:
        return spec, None

    new_spec = spec.model_copy(deep=True)
    new_spec.overnight.hotel_allowed = True

    record = RelaxationRecord(
        step=step,
        dimension="hotel_fallback",
        original_value=False,
        relaxed_value=True,
        reason="Enabled hotel fallback overnight to increase route coverage",
    )
    return new_spec, record


def _step5_out_and_back(
    spec: TripSpec,
    step: int,
) -> tuple[TripSpec, Optional[RelaxationRecord]]:
    """Allow out-and-back shape if loop preference was too restrictive."""
    if not spec.relaxation_policy.allow_out_and_back:
        return spec, None

    if spec.route_shape.preferred != "loop":
        return spec, None

    new_spec = spec.model_copy(deep=True)
    new_spec.route_shape.preferred = "out_and_back"

    record = RelaxationRecord(
        step=step,
        dimension="route_shape",
        original_value="loop",
        relaxed_value="out_and_back",
        reason="Relaxed loop requirement to out-and-back to expand viable route options",
    )
    return new_spec, record


_STEP_FUNCTIONS = [
    _step1_widen_distance,
    _step2_widen_surface,
    _step3_lower_overnight_tier,
    _step4_hotel_fallback,
    _step5_out_and_back,
]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def plan_with_relaxation(
    spec: TripSpec,
    db: Session,
) -> tuple[list[tuple[AssembledTrip, ScoreBreakdown]], list[RelaxationRecord]]:
    """
    Run the full planning pipeline with automatic constraint relaxation.

    Tries the original spec first. If fewer than N_MIN valid trips result,
    applies relaxation steps in cascade order until enough results are found
    or all steps are exhausted.

    Args:
        spec: Original TripSpec from the intent parser.
        db: SQLAlchemy session.

    Returns:
        Tuple of:
            - ranked_trips: List of (AssembledTrip, ScoreBreakdown) sorted by score.
              May be empty if all relaxation steps failed to produce results.
            - relaxations: List of RelaxationRecord entries for steps that fired.
    """
    applied_records: list[RelaxationRecord] = []
    relaxed_spec = spec.model_copy(deep=True)
    best_results: list[tuple[AssembledTrip, ScoreBreakdown]] = []

    for step_index in range(MAX_STEPS + 1):
        if step_index > 0:
            # Apply the next relaxation step
            fn = _STEP_FUNCTIONS[step_index - 1]
            relaxed_spec, record = fn(relaxed_spec, step_index)
            if record is None:
                logger.info("Relaxation step %d skipped (not applicable/permitted)", step_index)
                continue
            applied_records.append(record)
            logger.info(
                "Relaxation step %d applied: %s  %s -> %s",
                step_index, record.dimension, record.original_value, record.relaxed_value,
            )

        logger.info("Planning pipeline attempt (step %d)...", step_index)
        results = _try_pipeline(relaxed_spec, db)
        logger.info("  -> %d valid trips", len(results))

        if results:
            best_results = results

        if len(results) >= N_MIN_RESULTS:
            logger.info("Reached N_MIN=%d results at step %d — stopping relaxation", N_MIN_RESULTS, step_index)
            break

        if step_index == MAX_STEPS:
            logger.warning(
                "Exhausted all %d relaxation steps. Best result: %d trips.",
                MAX_STEPS, len(best_results),
            )

    if applied_records:
        logger.info(
            "Relaxation summary: %d steps applied (%s)",
            len(applied_records),
            ", ".join(r.dimension for r in applied_records),
        )

    return best_results, applied_records
