"""Code-QA stage: runs the target repo's lint/typecheck/format suite.

Mirrors :mod:`harness.services.reviewer`: one agent invocation per
iteration, pass/fail driven by the agent's exit code, and a markdown
report written to ``ctx.code_qa_path``. Tests (unit, integration, e2e)
are deliberately out of scope — see ``CODE_QA_PROMPT``.
"""

from __future__ import annotations

from harness.config import MAX_CODE_QA_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.cursor_agent import run_agent
from harness.logging import die, log
from harness.prompts import CODE_QA_PROMPT


def run_code_qa(ctx: HarnessContext, iteration: int) -> bool:
    assert ctx.code_qa_path
    abs_code_qa = ctx.repo / ctx.code_qa_path
    if abs_code_qa.exists():
        abs_code_qa.unlink()
    prompt = CODE_QA_PROMPT.format(code_qa_path=str(ctx.code_qa_path))
    code, _ = run_agent(prompt, ctx=ctx, stage="code-qa", iteration=iteration)
    if not abs_code_qa.exists():
        die(f"code-qa did not create {ctx.code_qa_path}")
    if code == 0:
        log(f"code-qa iteration {iteration}: PASS")
        return True
    log(f"code-qa iteration {iteration}: FAIL (exit {code})")
    return False


def append_final_code_qa_to_plan(ctx: HarnessContext) -> None:
    assert ctx.plan_path and ctx.code_qa_path
    abs_plan = ctx.repo / ctx.plan_path
    abs_code_qa = ctx.repo / ctx.code_qa_path
    body = abs_code_qa.read_text() if abs_code_qa.exists() else "(no code-qa file)"
    with abs_plan.open("a") as f:
        f.write("\n\n## Final code-qa (unresolved)\n\n")
        f.write(
            f"The harness exhausted its {MAX_CODE_QA_ITERATIONS} code-qa "
            "iterations without a passing run. The final code-qa output is "
            "preserved below.\n\n"
        )
        f.write(body.rstrip() + "\n")
    log(f"appended final code-qa report to {ctx.plan_path}")
