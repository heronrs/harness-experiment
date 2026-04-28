"""Unit tests for the one-shot ``harness ask`` path."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import orchestrator
from harness.services import ask as ask_module


def test_run_ask_forwards_prompt_and_returns_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_ephemeral(prompt, *, cwd, model, plan_mode=False):
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        captured["model"] = model
        captured["plan_mode"] = plan_mode
        return 0, "answer"

    monkeypatch.setattr(ask_module, "run_agent_ephemeral", fake_ephemeral)

    code = ask_module.run_ask(prompt="hello there", model="claude-test", cwd=tmp_path)

    assert code == 0
    assert captured == {
        "prompt": "hello there",
        "cwd": tmp_path,
        "model": "claude-test",
        "plan_mode": False,
    }


def test_run_ask_propagates_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_ephemeral(prompt, *, cwd, model, plan_mode=False):
        return 7, ""

    monkeypatch.setattr(ask_module, "run_agent_ephemeral", fake_ephemeral)
    assert ask_module.run_ask(prompt="x", model="m", cwd=tmp_path) == 7


def test_orchestrator_ask_delegates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_run_ask(*, prompt, model, cwd):
        seen["prompt"] = prompt
        seen["model"] = model
        seen["cwd"] = cwd
        return 0

    monkeypatch.setattr(orchestrator, "_run_ask", fake_run_ask)

    code = orchestrator.ask(prompt="ping", model="m", repo=tmp_path)

    assert code == 0
    assert seen == {"prompt": "ping", "model": "m", "cwd": tmp_path}
