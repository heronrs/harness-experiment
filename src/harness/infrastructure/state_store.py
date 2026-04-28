"""Checkpoint persistence and resume-token (de)serialization.

State files live at ``.harness/<slug>.state.json`` inside the target
repo. Tokens are base64url-encoded ``{repo, slug}`` payloads passed via
``harness continue <token>``.
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path

from harness.config import HARNESS_DIR
from harness.domain.models import HarnessContext, RunState
from harness.logging import die


def state_file_path(repo: Path, slug: str) -> Path:
    return repo / HARNESS_DIR / f"{slug}.state.json"


def state_file_exists(ctx: HarnessContext) -> bool:
    if not ctx.slug:
        return False
    return state_file_path(ctx.repo, ctx.slug).exists()


def save_state(ctx: HarnessContext, next_stage: str, iteration: int) -> None:
    assert ctx.slug
    state = RunState(
        task=ctx.task,
        model=ctx.model,
        repo=str(ctx.repo),
        slug=ctx.slug,
        next_stage=next_stage,
        iteration=iteration,
    )
    path = state_file_path(ctx.repo, ctx.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2))


def load_state(repo: Path, slug: str) -> RunState:
    path = state_file_path(repo, slug)
    if not path.exists():
        die(f"no state file found at {path}; cannot resume.")
    try:
        data = json.loads(path.read_text())
        return RunState(**data)
    except Exception as exc:
        die(f"state file {path} is malformed: {exc}")
    raise AssertionError("unreachable")


def encode_token(repo: Path, slug: str) -> str:
    payload = json.dumps({"repo": str(repo), "slug": slug})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_token(token: str) -> tuple[Path, str]:
    try:
        data = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
        return Path(data["repo"]), data["slug"]
    except Exception as exc:
        die(f"invalid continue token: {exc}")
    raise AssertionError("unreachable")


def cleanup_state(ctx: HarnessContext) -> None:
    if not ctx.slug:
        return
    path = state_file_path(ctx.repo, ctx.slug)
    path.unlink(missing_ok=True)
