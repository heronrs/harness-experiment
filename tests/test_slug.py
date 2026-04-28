"""Unit tests for slug sanitization."""

from __future__ import annotations

from harness.services.slug import sanitize_slug


def test_sanitize_slug_normal() -> None:
    assert sanitize_slug("add-health-endpoint") == "add-health-endpoint"


def test_sanitize_slug_strips_quotes_and_whitespace() -> None:
    assert sanitize_slug("  `Add Health Endpoint`  \n") == "add-health-endpoint"


def test_sanitize_slug_collapses_dashes_and_strips_invalid() -> None:
    assert sanitize_slug("add--health!!endpoint") == "add-healthendpoint"


def test_sanitize_slug_empty_returns_none() -> None:
    assert sanitize_slug("   ") is None
    assert sanitize_slug("!!!") is None
