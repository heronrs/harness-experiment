"""Implementer stage: edits the working tree per the plan.

The implementer is intentionally agnostic about *why* it's being invoked.
Callers (review phase, qa phase) supply a ``guidance`` string that is
embedded into the prompt; the implementer itself never branches on
stage-specific concerns.
"""

from __future__ import annotations

from harness.config import MAX_REVIEW_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.cursor_agent import run_agent
from harness.logging import die
from harness.prompts import IMPLEMENTER_PROMPT


def run_implementer(
    ctx: HarnessContext,
    iteration: int,
    *,
    guidance: str,
) -> None:
    assert ctx.plan_path
    prompt = IMPLEMENTER_PROMPT.format(
        plan_path=str(ctx.plan_path),
        iteration=iteration,
        max_iterations=MAX_REVIEW_ITERATIONS,
        review_guidance=guidance,
    )
    code, _ = run_agent(prompt, ctx=ctx, stage="implementer", iteration=iteration)
    if code != 0:
        die(f"implementer exited with code {code} on iteration {iteration}")
