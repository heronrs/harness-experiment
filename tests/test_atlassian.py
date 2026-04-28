"""Unit tests for infrastructure.atlassian."""

import pytest

from harness.infrastructure.atlassian import _parse_task_description


def test_parse_valid():
    text = (
        "<TASK_DESCRIPTION>\nAdd search\n\n"
        "User needs a search box.\n</TASK_DESCRIPTION>"
    )
    assert _parse_task_description(text) == "Add search\n\nUser needs a search box."


def test_parse_missing():
    assert _parse_task_description("nothing here") is None


def test_fetch_auth_retry(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_ephemeral(prompt, *, cwd, model, plan_mode=False):
        calls.append(len(calls))
        if len(calls) == 1:
            return 0, "AUTH_REQUIRED"
        return 0, "<TASK_DESCRIPTION>\nDo the thing\n</TASK_DESCRIPTION>"

    monkeypatch.setattr(
        "harness.infrastructure.atlassian.run_agent_ephemeral", fake_ephemeral
    )
    monkeypatch.setattr("builtins.input", lambda _: "")

    from harness.infrastructure.atlassian import fetch_jira_task

    result = fetch_jira_task(
        "https://jira.example.com/browse/FOO-1", model="m", repo=tmp_path
    )
    assert result == "Do the thing"
    assert len(calls) == 2


def test_fetch_auth_fails_twice(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_ephemeral(prompt, *, cwd, model, plan_mode=False):
        return 0, "AUTH_REQUIRED"

    monkeypatch.setattr(
        "harness.infrastructure.atlassian.run_agent_ephemeral", fake_ephemeral
    )
    monkeypatch.setattr("builtins.input", lambda _: "")

    from harness.infrastructure.atlassian import fetch_jira_task

    with pytest.raises(SystemExit):
        fetch_jira_task(
            "https://jira.example.com/browse/FOO-1", model="m", repo=tmp_path
        )
