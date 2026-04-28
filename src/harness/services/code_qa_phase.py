"""Code-QA phase coordinator: code_qa <-> implementer iteration loop.

Mirrors :mod:`harness.services.review_phase`. Runs the project's
lint/typecheck/format suite, and on failure dispatches the implementer
with code-qa-specific guidance.
"""

from __future__ import annotations

from harness.config import MAX_CODE_QA_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.state_store import cleanup_state, save_state
from harness.logging import die, log
from harness.prompts import IMPLEMENTER_CODE_QA_FOLLOWUP_GUIDANCE
from harness.services.code_qa import append_final_code_qa_to_plan, run_code_qa
from harness.services.implementer import run_implementer

CODE_QA_STAGES = frozenset({"code_qa", "implementer_code_qa_fix"})


def _implementer_guidance(ctx: HarnessContext) -> str:
    assert ctx.code_qa_path
    return IMPLEMENTER_CODE_QA_FOLLOWUP_GUIDANCE.format(
        code_qa_path=str(ctx.code_qa_path)
    )


def run_code_qa_phase(
    ctx: HarnessContext,
    *,
    start_iteration: int,
    start_stage: str,
) -> None:
    """Run the code-qa/implementer loop until qa passes or cap is hit.

    On exhaustion: appends the final code-qa report to the plan and
    exits via ``die``. On success: leaves checkpoint state at
    ``commit`` so the orchestrator can proceed to commit/PR.
    """
    assert start_stage in CODE_QA_STAGES, f"unexpected stage: {start_stage}"
    next_stage = start_stage

    for iteration in range(start_iteration, MAX_CODE_QA_ITERATIONS + 1):
        log(f"--- code-qa iteration {iteration}/{MAX_CODE_QA_ITERATIONS} ---")
        if next_stage == "implementer_code_qa_fix":
            save_state(ctx, "implementer_code_qa_fix", iteration)
            run_implementer(ctx, iteration, guidance=_implementer_guidance(ctx))
            save_state(ctx, "code_qa", iteration)
            next_stage = "code_qa"

        if run_code_qa(ctx, iteration):
            save_state(ctx, "commit", iteration)
            return
        next_stage = "implementer_code_qa_fix"

    cleanup_state(ctx)
    append_final_code_qa_to_plan(ctx)
    die(
        f"code-qa did not pass within {MAX_CODE_QA_ITERATIONS} iterations. "
        f"See {ctx.plan_path} for unresolved issues."
    )
