"""Slug validation and normalization."""

from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sanitize_slug(raw: str) -> str | None:
    candidate = raw.strip().strip("`'\"").lower()
    candidate = re.sub(r"\s+", "-", candidate)
    candidate = re.sub(r"[^a-z0-9-]", "", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    return candidate if candidate and SLUG_RE.match(candidate) else None
