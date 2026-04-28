"""Unit tests for the reviewer service."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.config import HARNESS_DIR
from harness.domain.models import HarnessContext
from harness.services import reviewer as reviewer_module


def _make_ctx(repo: Path, slug: str = "demo-task") -> HarnessContext:
    (repo / HARNESS_DIR).mkdir(parents=True, exist_ok=True)
    return HarnessContext(
        task="t",
        model="m",
        repo=repo,
        slug=slug,
        plan_path=HARNESS_DIR / f"{slug}.plan.md",
        review_path=HARNESS_DIR / f"{slug}.review.md",
        code_qa_path=HARNESS_DIR / f"{slug}.code_qa.md",
    )


def test_run_reviewer_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_ctx(tmp_path)
    abs_review = tmp_path / ctx.review_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        assert stage == "reviewer"
        abs_review.write_text("# review\n\nLGTM\n\nSTATUS: PASS\n")
        return 0, ""

    monkeypatch.setattr(reviewer_module, "run_agent", fake_agent)
    assert reviewer_module.run_reviewer(ctx, 1) is True


def test_run_reviewer_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_ctx(tmp_path)
    abs_review = tmp_path / ctx.review_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        abs_review.write_text("# review\n\nbug\n\nSTATUS: FAIL\n")
        return 1, ""

    monkeypatch.setattr(reviewer_module, "run_agent", fake_agent)
    assert reviewer_module.run_reviewer(ctx, 2) is False


def test_run_reviewer_fail_trailer_with_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: agent wrote STATUS: FAIL but exited 0.

    Before the fix this was misreported as PASS, the loop short-circuited
    on iteration 1, and the orchestrator advanced to PR creation. The
    trailer is now authoritative.
    """
    ctx = _make_ctx(tmp_path)
    abs_review = tmp_path / ctx.review_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        abs_review.write_text("# review\n\nbroken in two places\n\nSTATUS: FAIL\n")
        return 0, ""

    monkeypatch.setattr(reviewer_module, "run_agent", fake_agent)
    assert reviewer_module.run_reviewer(ctx, 1) is False


def test_run_reviewer_missing_file_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        return 0, ""

    monkeypatch.setattr(reviewer_module, "run_agent", fake_agent)
    with pytest.raises(SystemExit):
        reviewer_module.run_reviewer(ctx, 1)


def test_run_reviewer_missing_trailer_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    abs_review = tmp_path / ctx.review_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        abs_review.write_text("# review\n\nno trailer\n")
        return 0, ""

    monkeypatch.setattr(reviewer_module, "run_agent", fake_agent)
    with pytest.raises(SystemExit):
        reviewer_module.run_reviewer(ctx, 1)


def test_append_final_review_to_plan(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    abs_plan = tmp_path / ctx.plan_path  # type: ignore[operator]
    abs_review = tmp_path / ctx.review_path  # type: ignore[operator]
    abs_plan.write_text("# plan\n")
    abs_review.write_text("issue 1\nissue 2\nSTATUS: FAIL\n")

    reviewer_module.append_final_review_to_plan(ctx)

    final = abs_plan.read_text()
    assert "Final review (unresolved)" in final
    assert "issue 1" in final
    assert "STATUS: FAIL" in final
