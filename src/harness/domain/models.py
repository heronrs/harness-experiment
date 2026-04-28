"""Pure data structures shared across layers. No I/O, no side effects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class HarnessContext:
    task: str
    model: str
    repo: Path
    plan_path: Path | None = None
    review_path: Path | None = None
    slug: str | None = None
    branch_ts: str | None = None


@dataclass
class RunState:
    task: str
    model: str
    repo: str
    slug: str
    next_stage: str
    iteration: int
