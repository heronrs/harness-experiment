"""Implementer stage: edits the working tree per the plan."""

from __future__ import annotations

from harness.config import MAX_REVIEW_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.cursor_agent import run_agent
from harness.logging import die
from harness.prompts import (
    IMPLEMENTER_FIRST_ITERATION_GUIDANCE,
    IMPLEMENTER_FOLLOWUP_GUIDANCE,
    IMPLEMENTER_PROMPT,
)


def run_implementer(ctx: HarnessContext, iteration: int) -> None:
    assert ctx.plan_path and ctx.review_path
    if iteration == 1:
        guidance = IMPLEMENTER_FIRST_ITERATION_GUIDANCE
    else:
        guidance = IMPLEMENTER_FOLLOWUP_GUIDANCE.format(
            review_path=str(ctx.review_path)
        )
    prompt = IMPLEMENTER_PROMPT.format(
        plan_path=str(ctx.plan_path),
        iteration=iteration,
        max_iterations=MAX_REVIEW_ITERATIONS,
        review_guidance=guidance,
    )
    code, _ = run_agent(prompt, ctx=ctx, stage="implementer", iteration=iteration)
    if code != 0:
        die(f"implementer exited with code {code} on iteration {iteration}")
