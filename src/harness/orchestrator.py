"""High-level use case: run the full plan/implement/review/PR pipeline.

The orchestrator is the only place that knows about the full state
machine. Lower layers each handle a single concern; this module wires
them together and owns the resume/checkpoint flow.
"""

from __future__ import annotations

import sys
from pathlib import Path

from harness.config import HARNESS_DIR, MAX_REVIEW_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.git import (
    checkout_feature_branch_from_origin_main,
    rename_feature_branch_to_slug,
)
from harness.infrastructure.state_store import (
    cleanup_state,
    decode_token,
    encode_token,
    load_state,
    save_state,
    state_file_exists,
)
from harness.logging import die, log
from harness.services.implementer import run_implementer
from harness.services.planner import run_planner
from harness.services.pr import commit_and_open_pr
from harness.services.reviewer import append_final_review_to_plan, run_reviewer
from harness.services.workspace import ensure_harness_dir


def _print_resume_hint(ctx: HarnessContext) -> None:
    if ctx.slug and state_file_exists(ctx):
        token = encode_token(ctx.repo, ctx.slug)
        print(
            f"\n[harness] Run interrupted. Resume with:\n"
            f"  harness continue {token}",
            file=sys.stderr,
        )


def _run_loop(
    ctx: HarnessContext,
    *,
    next_stage: str,
    start_iteration: int,
    skip_pr: bool,
) -> None:
    try:
        if next_stage == "planner":
            checkout_feature_branch_from_origin_main(ctx)
            run_planner(ctx)
            rename_feature_branch_to_slug(ctx)
            save_state(ctx, "implementer", 1)
            next_stage = "implementer"
            start_iteration = 1

        passed = next_stage == "commit"

        if not passed:
            for iteration in range(start_iteration, MAX_REVIEW_ITERATIONS + 1):
                log(f"--- iteration {iteration}/{MAX_REVIEW_ITERATIONS} ---")
                if next_stage == "implementer":
                    save_state(ctx, "implementer", iteration)
                    run_implementer(ctx, iteration)
                    save_state(ctx, "reviewer", iteration)
                    next_stage = "reviewer"

                passed = run_reviewer(ctx, iteration)
                if passed:
                    save_state(ctx, "commit", iteration)
                    break
                next_stage = "implementer"

        if not passed:
            cleanup_state(ctx)
            append_final_review_to_plan(ctx)
            die(
                f"review did not pass within {MAX_REVIEW_ITERATIONS} iterations. "
                f"See {ctx.plan_path} for unresolved issues."
            )

        if skip_pr:
            log("--skip-pr set; stopping before commit/PR.")
            cleanup_state(ctx)
            return

        commit_and_open_pr(ctx)
        cleanup_state(ctx)
        log("done.")

    except SystemExit as exc:
        if exc.code != 0:
            _print_resume_hint(ctx)
        raise


def run_new_task(*, task: str, model: str, repo: Path, skip_pr: bool) -> None:
    ctx = HarnessContext(task=task, model=model, repo=repo)
    ensure_harness_dir(ctx.repo)
    log(f"task: {ctx.task}")
    log(f"repo: {ctx.repo}")
    log(f"model: {ctx.model}")
    _run_loop(ctx, next_stage="planner", start_iteration=1, skip_pr=skip_pr)


def resume_from_token(
    *, token: str, model_override: str | None, skip_pr: bool
) -> None:
    repo_path, slug = decode_token(token)
    state = load_state(repo_path, slug)
    ctx = HarnessContext(
        task=state.task,
        model=model_override or state.model,
        repo=repo_path,
        slug=state.slug,
        plan_path=HARNESS_DIR / f"{slug}.plan.md",
        review_path=HARNESS_DIR / f"{slug}.review.md",
    )
    ensure_harness_dir(ctx.repo)
    log(f"task: {ctx.task}")
    log(f"repo: {ctx.repo}")
    log(f"model: {ctx.model}")
    log(f"resuming from stage={state.next_stage} iteration={state.iteration}")
    _run_loop(
        ctx,
        next_stage=state.next_stage,
        start_iteration=state.iteration,
        skip_pr=skip_pr,
    )
