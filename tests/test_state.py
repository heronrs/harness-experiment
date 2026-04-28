"""Unit tests for the checkpoint/resume state system."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.domain.models import HarnessContext
from harness.infrastructure.state_store import (
    decode_token,
    encode_token,
    load_state,
    save_state,
)


def test_encode_decode_token_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "my-repo"
    slug = "add-health-endpoint"

    token = encode_token(repo, slug)
    decoded_repo, decoded_slug = decode_token(token)

    assert decoded_repo == repo
    assert decoded_slug == slug


def test_save_load_state_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".harness").mkdir(parents=True)

    ctx = HarnessContext(
        task="add a /health endpoint",
        model="claude-test",
        repo=repo,
        slug="add-health-endpoint",
        plan_path=Path(".harness/add-health-endpoint.plan.md"),
        review_path=Path(".harness/add-health-endpoint.review.md"),
    )

    save_state(ctx, "reviewer", 2)
    loaded = load_state(repo, "add-health-endpoint")

    assert loaded.task == ctx.task
    assert loaded.model == ctx.model
    assert loaded.repo == str(repo)
    assert loaded.slug == ctx.slug
    assert loaded.next_stage == "reviewer"
    assert loaded.iteration == 2


def test_decode_token_invalid() -> None:
    with pytest.raises(SystemExit):
        decode_token("this-is-not-valid-base64!!!!")


def test_load_state_missing_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".harness").mkdir()

    with pytest.raises(SystemExit):
        load_state(repo, "nonexistent-slug")
