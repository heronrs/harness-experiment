"""Reviewer stage: writes a markdown verdict and returns pass/fail."""

from __future__ import annotations

from harness.config import MAX_REVIEW_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.cursor_agent import run_agent
from harness.logging import die, log
from harness.prompts import REVIEWER_PROMPT


def run_reviewer(ctx: HarnessContext, iteration: int) -> bool:
    assert ctx.plan_path and ctx.review_path
    abs_review = ctx.repo / ctx.review_path
    if abs_review.exists():
        abs_review.unlink()
    prompt = REVIEWER_PROMPT.format(
        plan_path=str(ctx.plan_path),
        review_path=str(ctx.review_path),
    )
    code, _ = run_agent(prompt, ctx=ctx, stage="reviewer", iteration=iteration)
    if not abs_review.exists():
        die(f"reviewer did not create {ctx.review_path}")
    if code == 0:
        log(f"reviewer iteration {iteration}: PASS")
        return True
    log(f"reviewer iteration {iteration}: FAIL (exit {code})")
    return False


def append_final_review_to_plan(ctx: HarnessContext) -> None:
    assert ctx.plan_path and ctx.review_path
    abs_plan = ctx.repo / ctx.plan_path
    abs_review = ctx.repo / ctx.review_path
    review_body = abs_review.read_text() if abs_review.exists() else "(no review file)"
    with abs_plan.open("a") as f:
        f.write("\n\n## Final review (unresolved)\n\n")
        f.write(
            f"The harness exhausted its {MAX_REVIEW_ITERATIONS} review iterations "
            "without a passing review. The final reviewer output is preserved below.\n\n"
        )
        f.write(review_body.rstrip() + "\n")
    log(f"appended final review to {ctx.plan_path}")
