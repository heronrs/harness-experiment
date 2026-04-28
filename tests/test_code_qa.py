"""Unit tests for the code-qa service."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.config import HARNESS_DIR
from harness.domain.models import HarnessContext
from harness.services import code_qa as code_qa_module


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


def test_run_code_qa_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_ctx(tmp_path)
    abs_code_qa = tmp_path / ctx.code_qa_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        assert stage == "code-qa"
        abs_code_qa.write_text("# qa\n\nSTATUS: PASS\n")
        return 0, ""

    monkeypatch.setattr(code_qa_module, "run_agent", fake_agent)
    assert code_qa_module.run_code_qa(ctx, 1) is True


def test_run_code_qa_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_ctx(tmp_path)
    abs_code_qa = tmp_path / ctx.code_qa_path  # type: ignore[operator]

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        abs_code_qa.write_text("# qa\n\nSTATUS: FAIL\n")
        return 1, ""

    monkeypatch.setattr(code_qa_module, "run_agent", fake_agent)
    assert code_qa_module.run_code_qa(ctx, 2) is False


def test_run_code_qa_missing_file_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        return 0, ""

    monkeypatch.setattr(code_qa_module, "run_agent", fake_agent)
    with pytest.raises(SystemExit):
        code_qa_module.run_code_qa(ctx, 1)


def test_run_code_qa_clears_stale_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    abs_code_qa = tmp_path / ctx.code_qa_path  # type: ignore[operator]
    abs_code_qa.write_text("stale content\n")

    seen_before: dict[str, bool] = {}

    def fake_agent(prompt, *, ctx, stage, iteration, plan_mode=False):
        seen_before["existed"] = abs_code_qa.exists()
        abs_code_qa.write_text("# qa\nSTATUS: PASS\n")
        return 0, ""

    monkeypatch.setattr(code_qa_module, "run_agent", fake_agent)
    code_qa_module.run_code_qa(ctx, 1)
    assert seen_before["existed"] is False


def test_append_final_code_qa_to_plan(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    abs_plan = tmp_path / ctx.plan_path  # type: ignore[operator]
    abs_code_qa = tmp_path / ctx.code_qa_path  # type: ignore[operator]
    abs_plan.write_text("# plan\n")
    abs_code_qa.write_text("ruff: 3 errors\nSTATUS: FAIL\n")

    code_qa_module.append_final_code_qa_to_plan(ctx)

    final = abs_plan.read_text()
    assert "Final code-qa (unresolved)" in final
    assert "ruff: 3 errors" in final
    assert "STATUS: FAIL" in final
