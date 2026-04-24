#!/usr/bin/env python3
"""
Minimal AI coding harness built on top of the Cursor CLI.

Flow: plan -> (implement -> review) x up to 3 -> commit + draft PR.

Usage:
    python harness.py "add a /health endpoint to the API"
    python harness.py --model claude-4.6-sonnet-medium-thinking "fix the flaky test"

The target repo is the current working directory.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "claude-4.6-sonnet-medium-thinking"
MAX_REVIEW_ITERATIONS = 3
AGENT_TIMEOUT_SECONDS = 15 * 60
HARNESS_DIR = Path(".harness")
LOGS_DIR = HARNESS_DIR / "logs"


PLANNER_PROMPT = """\
You are the PLANNER stage of an automated coding harness.

Task from the user:
<<<
{task}
>>>

Do the following, in this exact order:

1. Come up with a short kebab-case slug that describes the task
   (lowercase, hyphen-separated, at most 6 words, ASCII only, no file extension,
   e.g. `add-health-endpoint`).
2. Write that slug and NOTHING ELSE (no quotes, no surrounding whitespace,
   no trailing newline beyond one) to the file `{slug_path}`.
   This file MUST exist when you finish, or the harness will abort.
3. Then read the repository structure as needed and write a concrete,
   step-by-step implementation plan to `{plan_path}`. The plan should
   cover: files to touch, new functions/classes, data flow,
   edge cases, and a short test strategy.

Constraints:
- You are in plan mode: you may only write to `{slug_path}` and `{plan_path}`.
  Do NOT edit any other files.
- Keep the plan focused and actionable. No fluff.
"""


IMPLEMENTER_PROMPT = """\
You are the IMPLEMENTER stage of an automated coding harness.
Iteration: {iteration} of {max_iterations}.

Read `{plan_path}` in full and implement the task it describes.

{review_guidance}

Rules:
- Make all code changes required by the plan.
- Run any quick local checks you have available (formatters, linters, type
  checkers, unit tests) and fix issues they surface.
- DO NOT commit, push, or create branches. Leave changes in the working tree.
- DO NOT modify files under `.harness/` — they are harness bookkeeping.
"""


IMPLEMENTER_FIRST_ITERATION_GUIDANCE = (
    "This is the first implementation attempt, so there is no prior review yet."
)


IMPLEMENTER_FOLLOWUP_GUIDANCE = """\
A previous review found issues. Read `{review_path}` in full and address
EVERY problem it raises before finishing. If the review asks you to change
behavior, change behavior; if it asks for tests, add tests.
"""


REVIEWER_PROMPT = """\
You are the REVIEWER stage of an automated coding harness.

Your job:
1. Inspect the current working tree changes (use `git status` and
   `git diff` — compare against `origin/main` if it exists, otherwise
   against `HEAD`).
2. Evaluate the diff against `{plan_path}` for:
   - correctness and obvious bugs
   - missing test coverage for new behavior
   - security concerns
   - adherence to the plan
3. Overwrite `{review_path}` with your findings in markdown. Be specific:
   cite file paths and line numbers. If there are no issues, say so briefly.
4. The VERY LAST line of `{review_path}` MUST be exactly one of:
     STATUS: PASS
     STATUS: FAIL
5. After writing the file, exit the agent with:
     - exit code 0 if the change is merge-ready (STATUS: PASS)
     - exit code 1 if it is not (STATUS: FAIL)
   You can do this by running `exit 0` or `exit 1` in a shell tool call
   as your final action.

Rules:
- Do NOT edit any source files. The only file you may write is `{review_path}`.
- Be strict but fair. A tiny nit is not a FAIL; a real bug or missing test is.
"""


@dataclass
class HarnessContext:
    task: str
    model: str
    repo: Path
    plan_path: Path | None = None
    review_path: Path | None = None
    slug: str | None = None


def die(msg: str, code: int = 1) -> None:
    print(f"[harness] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str) -> None:
    print(f"[harness] {msg}", flush=True)


def ensure_cursor_agent() -> str:
    binary = shutil.which("cursor-agent")
    if not binary:
        die("`cursor-agent` not found on PATH. Install the Cursor CLI first.")
    return binary


def ensure_harness_dir(repo: Path) -> None:
    (repo / LOGS_DIR).mkdir(parents=True, exist_ok=True)
    gitignore = repo / ".gitignore"
    line = ".harness/"
    if gitignore.exists():
        existing = gitignore.read_text()
        if line not in existing.splitlines():
            with gitignore.open("a") as f:
                if not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"{line}\n")
    else:
        gitignore.write_text(f"{line}\n")


def run_agent(
    prompt: str,
    *,
    ctx: HarnessContext,
    stage: str,
    iteration: int,
    plan_mode: bool = False,
) -> tuple[int, str]:
    """Invoke `cursor-agent -p` non-interactively and tee output to a log file."""
    binary = ensure_cursor_agent()
    slug_part = ctx.slug or "bootstrap"
    log_path = ctx.repo / LOGS_DIR / f"{slug_part}-{stage}-{iteration}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        binary,
        "--print",
        "--force",
        "--output-format",
        "text",
        "--model",
        ctx.model,
    ]
    if plan_mode:
        cmd += ["--mode", "plan"]
    cmd.append(prompt)

    log(f"stage={stage} iter={iteration} model={ctx.model} plan_mode={plan_mode}")
    log(f"log -> {log_path}")

    with log_path.open("w") as logfile:
        logfile.write(f"$ {' '.join(cmd[:-1])} <prompt>\n")
        logfile.write(f"--- PROMPT ---\n{prompt}\n--- OUTPUT ---\n")
        logfile.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=ctx.repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        stdout_chunks: list[str] = []
        start = time.time()
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                stdout_chunks.append(line)
                logfile.write(line)
                logfile.flush()
                sys.stdout.write(line)
                sys.stdout.flush()
                if time.time() - start > AGENT_TIMEOUT_SECONDS:
                    proc.kill()
                    die(f"agent stage '{stage}' timed out after {AGENT_TIMEOUT_SECONDS}s")
        finally:
            proc.wait()

    stdout = "".join(stdout_chunks)
    return proc.returncode, stdout


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sanitize_slug(raw: str) -> str | None:
    candidate = raw.strip().strip("`'\"").lower()
    candidate = re.sub(r"\s+", "-", candidate)
    candidate = re.sub(r"[^a-z0-9-]", "", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    return candidate if candidate and SLUG_RE.match(candidate) else None


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
    code, _ = run_agent(
        prompt, ctx=ctx, stage="planner", iteration=0, plan_mode=True
    )
    if code != 0:
        die(f"planner exited with code {code}")

    if not abs_slug.exists():
        die(
            f"planner did not create {slug_path}. "
            "Check the planner log for details."
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

    abs_plan = ctx.repo / ctx.plan_path
    if abs_tmp_plan.exists():
        abs_tmp_plan.replace(abs_plan)
    if not abs_plan.exists():
        die(f"planner did not create {ctx.plan_path}")
    abs_slug.unlink(missing_ok=True)
    log(f"slug='{slug}' plan={ctx.plan_path}")


def run_implementer(ctx: HarnessContext, iteration: int) -> None:
    assert ctx.plan_path and ctx.review_path
    if iteration == 1:
        guidance = IMPLEMENTER_FIRST_ITERATION_GUIDANCE
    else:
        guidance = IMPLEMENTER_FOLLOWUP_GUIDANCE.format(review_path=str(ctx.review_path))
    prompt = IMPLEMENTER_PROMPT.format(
        plan_path=str(ctx.plan_path),
        iteration=iteration,
        max_iterations=MAX_REVIEW_ITERATIONS,
        review_guidance=guidance,
    )
    code, _ = run_agent(prompt, ctx=ctx, stage="implementer", iteration=iteration)
    if code != 0:
        die(f"implementer exited with code {code} on iteration {iteration}")


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


def sh(cmd: list[str], *, cwd: Path, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )


def commit_and_open_pr(ctx: HarnessContext) -> None:
    assert ctx.slug and ctx.plan_path and ctx.review_path
    if not shutil.which("gh"):
        die("`gh` CLI not found; cannot open a PR.")

    ts = time.strftime("%Y%m%d-%H%M%S")
    branch = f"harness/{ctx.slug}-{ts}"
    sh(["git", "checkout", "-b", branch], cwd=ctx.repo)

    status = sh(
        ["git", "status", "--porcelain"], cwd=ctx.repo, capture=True
    ).stdout.strip()
    if not status:
        die("nothing to commit — implementer produced no changes.")

    sh(["git", "add", "-A"], cwd=ctx.repo)
    commit_msg = f"{ctx.slug}: automated harness commit\n\nTask: {ctx.task}\n"
    sh(["git", "commit", "-m", commit_msg], cwd=ctx.repo)
    sh(["git", "push", "-u", "origin", "HEAD"], cwd=ctx.repo)

    plan_body = (ctx.repo / ctx.plan_path).read_text()
    review_body = (
        (ctx.repo / ctx.review_path).read_text()
        if (ctx.repo / ctx.review_path).exists()
        else "(no review file)"
    )
    pr_body = (
        f"## Task\n\n{ctx.task}\n\n"
        f"## Plan\n\n{plan_body}\n\n"
        f"## Final review\n\n{review_body}\n\n"
        f"---\n_Generated by the AI harness experiment._\n"
    )
    title = f"[harness] {ctx.slug}"
    sh(
        ["gh", "pr", "create", "--draft", "--title", title, "--body", pr_body],
        cwd=ctx.repo,
    )
    log("draft PR opened.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Natural-language description of the task.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"cursor-agent model slug (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--repo",
        default=os.getcwd(),
        help="Path to the target git repository (default: cwd).",
    )
    parser.add_argument(
        "--skip-pr",
        action="store_true",
        help="Run plan + implement + review loop but skip commit/push/PR.",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        die(f"{repo} is not a git repository.")

    ctx = HarnessContext(task=args.task, model=args.model, repo=repo)
    ensure_harness_dir(ctx.repo)

    log(f"task: {ctx.task}")
    log(f"repo: {ctx.repo}")
    log(f"model: {ctx.model}")

    run_planner(ctx)

    passed = False
    for iteration in range(1, MAX_REVIEW_ITERATIONS + 1):
        log(f"--- iteration {iteration}/{MAX_REVIEW_ITERATIONS} ---")
        run_implementer(ctx, iteration)
        if run_reviewer(ctx, iteration):
            passed = True
            break

    if not passed:
        append_final_review_to_plan(ctx)
        die(
            f"review did not pass within {MAX_REVIEW_ITERATIONS} iterations. "
            f"See {ctx.plan_path} for unresolved issues."
        )

    if args.skip_pr:
        log("--skip-pr set; stopping before commit/PR.")
        return

    commit_and_open_pr(ctx)
    log("done.")


if __name__ == "__main__":
    main()
