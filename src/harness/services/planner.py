"""Planner stage: produces a slug and a plan markdown file."""

from __future__ import annotations

from harness.config import HARNESS_DIR
from harness.domain.models import HarnessContext
from harness.infrastructure.cursor_agent import run_agent
from harness.logging import die, log
from harness.prompts import PLANNER_PROMPT
from harness.services.slug import sanitize_slug


def run_planner(ctx: HarnessContext) -> None:
    tmp_plan_path = HARNESS_DIR / "_pending.plan.md"
    slug_path = HARNESS_DIR / "_pending.slug"
    abs_slug = ctx.repo / slug_path
    abs_tmp_plan = ctx.repo / tmp_plan_path
    for p in (abs_slug, abs_tmp_plan):
        if p.exists():
            p.unlink()

    prompt = PLANNER_PROMPT.format(
        task=ctx.task,
        plan_path=str(tmp_plan_path),
        slug_path=str(slug_path),
    )
    code, _ = run_agent(prompt, ctx=ctx, stage="planner", iteration=0, plan_mode=True)
    if code != 0:
        die(f"planner exited with code {code}")

    if not abs_slug.exists():
        die(
            f"planner did not create {slug_path}. " "Check the planner log for details."
        )
    slug = sanitize_slug(abs_slug.read_text())
    if not slug:
        die(
            f"planner wrote an invalid slug to {slug_path}: "
            f"{abs_slug.read_text()!r}"
        )

    ctx.slug = slug
    ctx.plan_path = HARNESS_DIR / f"{slug}.plan.md"
    ctx.review_path = HARNESS_DIR / f"{slug}.review.md"
    ctx.code_qa_path = HARNESS_DIR / f"{slug}.code_qa.md"

    abs_plan = ctx.repo / ctx.plan_path
    if abs_tmp_plan.exists():
        abs_tmp_plan.replace(abs_plan)
    if not abs_plan.exists():
        die(f"planner did not create {ctx.plan_path}")
    abs_slug.unlink(missing_ok=True)
    log(f"slug='{slug}' plan={ctx.plan_path}")
