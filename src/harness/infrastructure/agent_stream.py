"""Render ``cursor-agent --output-format stream-json`` events for humans.

The agent emits one JSON object per line. We stream-parse them and turn
each into (at most) one short text line for the terminal. The raw JSON
is preserved separately by the caller — this module only handles the
human-readable rendering.

Pure functions over dicts / strings: no I/O, no subprocess, no global
state. That makes the renderer trivially unit-testable with fixture
events.

Event shapes were observed against cursor-agent at the time of writing
and are best-effort: unknown ``type`` values are ignored, and missing
fields fall through to a defensive default. We deliberately do NOT
validate against a strict schema, because cursor-agent's stream-json
format is not versioned.
"""

from __future__ import annotations

import json
from typing import Any

# ANSI color codes. Keep this tiny rather than pulling in a colors library —
# we only want a few muted styles and the rest of the harness already uses
# Rich for high-level logging.
_DIM = "\x1b[2m"
_CYAN = "\x1b[36m"
_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_RESET = "\x1b[0m"


def _is_text_delta(event: dict[str, Any]) -> bool:
    """True iff this assistant event is a partial text delta.

    The agent emits, for each assistant message:
      - one event per token (with ``timestamp_ms``) — these are deltas,
      - one final consolidated event (without ``timestamp_ms``) carrying
        the full text.

    Rendering both would double-print, so we render only the deltas.
    """
    return "timestamp_ms" in event


def _extract_text(event: dict[str, Any]) -> str:
    msg = event.get("message") or {}
    parts: list[str] = []
    for block in msg.get("content") or []:
        if block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def _summarize_tool_call(tool_call: dict[str, Any]) -> str:
    """Best-effort one-liner describing a tool call.

    Tool calls are polymorphic: each tool wraps its args in a typed key
    like ``shellToolCall``. We pick the first such key we recognize
    and extract a human-meaningful summary (command, file path, etc.).
    Unknown tools fall back to the wrapper key name.
    """
    if not isinstance(tool_call, dict):
        return "tool"
    for key, payload in tool_call.items():
        if not isinstance(payload, dict):
            continue
        args = payload.get("args") or {}
        desc = payload.get("description") or args.get("description")
        if key == "shellToolCall":
            cmd = args.get("command") or "?"
            return f"shell: {cmd}"
        if key == "fileToolCall":
            path = args.get("path") or args.get("filePath") or "?"
            return f"file: {path}"
        if desc:
            return f"{key}: {desc}"
        return key
    return "tool"


def _summarize_tool_result(tool_call: dict[str, Any]) -> str | None:
    """Concise summary of a tool's result (exit code, line counts)."""
    if not isinstance(tool_call, dict):
        return None
    for payload in tool_call.values():
        if not isinstance(payload, dict):
            continue
        result = payload.get("result")
        if not isinstance(result, dict):
            continue
        success = result.get("success")
        if isinstance(success, dict):
            exit_code = success.get("exitCode")
            stdout = success.get("stdout") or ""
            line_count = stdout.count("\n")
            return f"exit={exit_code} ({line_count} lines)"
        if "error" in result or result.get("isError"):
            err = result.get("error") or "error"
            return f"error: {err}"
    return None


def classify_delta(event: dict[str, Any]) -> tuple[str, str] | None:
    """If ``event`` is a streaming token-delta, return ``(kind, text)``.

    ``kind`` is ``"assistant"`` or ``"thinking"``. Returns ``None`` for
    any non-delta event (the caller should fall back to ``render_event``).

    Splitting deltas out from full-event rendering lets the streaming
    layer coalesce consecutive same-kind deltas onto one line — the
    per-event prefix (e.g. ``[thinking]``) is added only at stream-start
    by the caller.
    """
    etype = event.get("type")
    if etype == "assistant":
        if not _is_text_delta(event):
            return None
        text = _extract_text(event)
        return ("assistant", text) if text else None
    if etype == "thinking" and _is_text_delta(event):
        text = _extract_text(event) or event.get("text") or ""
        return ("thinking", text) if text else None
    return None


def delta_stream_prefix(kind: str) -> str:
    """ANSI-colored prefix to emit when a new delta stream of ``kind`` starts."""
    if kind == "thinking":
        return f"{_DIM}[thinking] "
    return ""


def delta_stream_suffix(kind: str) -> str:
    """ANSI reset to emit when a delta stream of ``kind`` ends."""
    if kind == "thinking":
        return _RESET
    return ""


def render_event(event: dict[str, Any]) -> str | None:
    """Render a single stream-json event for human consumption.

    Returns ``None`` for events we deliberately suppress (final
    consolidated assistant messages, the ``user`` echo, etc.).
    """
    etype = event.get("type")

    if etype == "system":
        subtype = event.get("subtype") or "?"
        model = event.get("model")
        suffix = f" model={model}" if model else ""
        return f"{_DIM}[system:{subtype}]{suffix}{_RESET}"

    if etype == "assistant":
        if not _is_text_delta(event):
            return None
        text = _extract_text(event)
        return text or None

    if etype == "thinking":
        # Streaming deltas are coalesced by the caller via ``classify_delta``
        # so we don't return them here. A non-delta thinking event (no
        # ``timestamp_ms``) is rare but still rendered as a standalone line.
        if _is_text_delta(event):
            return None
        text = _extract_text(event) or event.get("text") or ""
        if not text:
            return None
        return f"{_DIM}[thinking] {text}{_RESET}"

    if etype == "tool_call":
        subtype = event.get("subtype")
        tool_call = event.get("tool_call") or {}
        if subtype == "started":
            summary = _summarize_tool_call(tool_call)
            return f"{_CYAN}[tool] {summary}{_RESET}"
        if subtype == "completed":
            result_summary = _summarize_tool_result(tool_call)
            if result_summary is None:
                return None
            color = _RED if result_summary.startswith("error") else _GREEN
            return f"{color}[tool ✓] {result_summary}{_RESET}"
        return None

    if etype == "result":
        if event.get("is_error") or event.get("subtype") == "error":
            return f"{_RED}[result] error: {event.get('result') or '?'}{_RESET}"
        usage = event.get("usage") or {}
        in_tok = usage.get("inputTokens", "?")
        out_tok = usage.get("outputTokens", "?")
        dur_ms = event.get("duration_ms", "?")
        return f"{_DIM}[result] {dur_ms}ms in={in_tok} out={out_tok}{_RESET}"

    if etype == "error":
        msg = event.get("message") or event.get("error") or "?"
        return f"{_RED}[error] {msg}{_RESET}"

    if etype == "user":
        return None

    return f"{_YELLOW}[unknown:{etype}]{_RESET}"


def parse_event_line(line: str) -> dict[str, Any] | None:
    """Parse one stream-json line into a dict, or ``None`` on malformed input.

    Defensive: cursor-agent's format isn't versioned, so a non-JSON line
    (banner, warning, etc.) shouldn't crash the harness.
    """
    line = line.strip()
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed
