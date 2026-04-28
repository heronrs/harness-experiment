"""Unit tests for the code-qa phase coordinator."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.config import HARNESS_DIR, MAX_CODE_QA_ITERATIONS
from harness.domain.models import HarnessContext
from harness.infrastructure.state_store import load_state
from harness.services import code_qa_phase as code_qa_phase_module


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


def test_code_qa_phase_passes_first_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    impl_calls: list[int] = []

    def fake_qa(ctx, iteration):
        return True

    def fake_impl(ctx, iteration, *, guidance):
        impl_calls.append(iteration)

    monkeypatch.setattr(code_qa_phase_module, "run_code_qa", fake_qa)
    monkeypatch.setattr(code_qa_phase_module, "run_implementer", fake_impl)

    code_qa_phase_module.run_code_qa_phase(
        ctx, start_iteration=1, start_stage="code_qa"
    )

    assert impl_calls == []
    assert load_state(tmp_path, ctx.slug).next_stage == "commit"  # type: ignore[arg-type]


def test_code_qa_phase_fail_then_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    qa_results = iter([False, True])
    impl_calls: list[tuple[int, str]] = []

    def fake_qa(ctx, iteration):
        return next(qa_results)

    def fake_impl(ctx, iteration, *, guidance):
        impl_calls.append((iteration, guidance))

    monkeypatch.setattr(code_qa_phase_module, "run_code_qa", fake_qa)
    monkeypatch.setattr(code_qa_phase_module, "run_implementer", fake_impl)

    code_qa_phase_module.run_code_qa_phase(
        ctx, start_iteration=1, start_stage="code_qa"
    )

    assert len(impl_calls) == 1
    iteration, guidance = impl_calls[0]
    assert iteration == 2
    assert str(ctx.code_qa_path) in guidance
    assert load_state(tmp_path, ctx.slug).next_stage == "commit"  # type: ignore[arg-type]


def test_code_qa_phase_exhausts_and_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    abs_plan = tmp_path / ctx.plan_path  # type: ignore[operator]
    abs_code_qa = tmp_path / ctx.code_qa_path  # type: ignore[operator]
    abs_plan.write_text("# plan\n")
    abs_code_qa.write_text("STATUS: FAIL\n")

    def fake_qa(ctx, iteration):
        return False

    def fake_impl(ctx, iteration, *, guidance):
        return None

    monkeypatch.setattr(code_qa_phase_module, "run_code_qa", fake_qa)
    monkeypatch.setattr(code_qa_phase_module, "run_implementer", fake_impl)

    with pytest.raises(SystemExit):
        code_qa_phase_module.run_code_qa_phase(
            ctx, start_iteration=1, start_stage="code_qa"
        )

    assert "Final code-qa (unresolved)" in abs_plan.read_text()


def test_code_qa_phase_resume_from_implementer_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _make_ctx(tmp_path)
    qa_results = iter([True])
    impl_calls: list[int] = []

    def fake_qa(ctx, iteration):
        return next(qa_results)

    def fake_impl(ctx, iteration, *, guidance):
        impl_calls.append(iteration)

    monkeypatch.setattr(code_qa_phase_module, "run_code_qa", fake_qa)
    monkeypatch.setattr(code_qa_phase_module, "run_implementer", fake_impl)

    code_qa_phase_module.run_code_qa_phase(
        ctx, start_iteration=2, start_stage="implementer_code_qa_fix"
    )

    assert impl_calls == [2]


def test_max_code_qa_iterations_is_three() -> None:
    assert MAX_CODE_QA_ITERATIONS == 3
