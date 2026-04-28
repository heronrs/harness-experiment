"""Review phase coordinator: implementer <-> reviewer iteration loop.

Owns the loop that was previously inlined in :mod:`harness.orchestrator`.
Encapsulating it here keeps the orchestrator a flat sequence of phases
and makes it cheap to add new phases without editing existing ones
(Open/Closed).
"""

from __future__ import annotations

from harness.config import MAX_REVIEW_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.state_store import cleanup_state, save_state
from harness.logging import die, log
from harness.prompts import (
    IMPLEMENTER_FIRST_ITERATION_GUIDANCE,
    IMPLEMENTER_REVIEW_FOLLOWUP_GUIDANCE,
)
from harness.services.implementer import run_implementer
from harness.services.reviewer import append_final_review_to_plan, run_reviewer

REVIEW_STAGES = frozenset({"implementer", "reviewer"})


def _implementer_guidance(ctx: HarnessContext, iteration: int) -> str:
    if iteration == 1:
        return IMPLEMENTER_FIRST_ITERATION_GUIDANCE
    assert ctx.review_path
    return IMPLEMENTER_REVIEW_FOLLOWUP_GUIDANCE.format(review_path=str(ctx.review_path))


def run_review_phase(
    ctx: HarnessContext,
    *,
    start_iteration: int,
    start_stage: str,
) -> None:
    """Run the implementer/reviewer loop until review passes or cap is hit.

    On exhaustion: appends the final review to the plan and exits via
    ``die``. On success: leaves checkpoint state at ``code_qa`` so the
    next phase picks up cleanly.
    """
    assert start_stage in REVIEW_STAGES, f"unexpected stage: {start_stage}"
    next_stage = start_stage

    for iteration in range(start_iteration, MAX_REVIEW_ITERATIONS + 1):
        log(f"--- review iteration {iteration}/{MAX_REVIEW_ITERATIONS} ---")
        if next_stage == "implementer":
            save_state(ctx, "implementer", iteration)
            run_implementer(
                ctx, iteration, guidance=_implementer_guidance(ctx, iteration)
            )
            save_state(ctx, "reviewer", iteration)
            next_stage = "reviewer"

        if run_reviewer(ctx, iteration):
            save_state(ctx, "code_qa", 1)
            return
        next_stage = "implementer"

    cleanup_state(ctx)
    append_final_review_to_plan(ctx)
    die(
        f"review did not pass within {MAX_REVIEW_ITERATIONS} iterations. "
        f"See {ctx.plan_path} for unresolved issues."
    )
