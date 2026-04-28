"""Unit tests for the cursor-agent stream-json renderer."""

from __future__ import annotations

from harness.infrastructure.agent_stream import (
    classify_delta,
    delta_stream_prefix,
    delta_stream_suffix,
    parse_event_line,
    render_event,
)


def test_parse_event_line_valid() -> None:
    assert parse_event_line('{"type": "system"}\n') == {"type": "system"}


def test_parse_event_line_blank() -> None:
    assert parse_event_line("") is None
    assert parse_event_line("   \n") is None


def test_parse_event_line_garbage() -> None:
    assert parse_event_line("not json at all") is None


def test_parse_event_line_non_object() -> None:
    assert parse_event_line('"a string"') is None
    assert parse_event_line("[1, 2, 3]") is None


def test_render_system_init() -> None:
    out = render_event({"type": "system", "subtype": "init", "model": "Sonnet 4.6"})
    assert out is not None
    assert "[system:init]" in out
    assert "Sonnet 4.6" in out


def test_render_assistant_delta_returns_text() -> None:
    event = {
        "type": "assistant",
        "timestamp_ms": 123,
        "message": {"content": [{"type": "text", "text": "hello"}]},
    }
    assert render_event(event) == "hello"


def test_render_assistant_consolidated_message_suppressed() -> None:
    # Final consolidated message has no timestamp_ms; rendering it would
    # double-print the answer.
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "pong"}]},
    }
    assert render_event(event) is None


def test_render_user_event_suppressed() -> None:
    assert render_event({"type": "user", "message": {}}) is None


def test_render_tool_call_started_shell() -> None:
    event = {
        "type": "tool_call",
        "subtype": "started",
        "tool_call": {
            "shellToolCall": {
                "args": {"command": "echo hello"},
                "description": "Run echo hello",
            }
        },
    }
    out = render_event(event)
    assert out is not None
    assert "[tool]" in out
    assert "echo hello" in out


def test_render_tool_call_completed_success() -> None:
    event = {
        "type": "tool_call",
        "subtype": "completed",
        "tool_call": {
            "shellToolCall": {
                "args": {"command": "echo hello"},
                "result": {
                    "success": {
                        "exitCode": 0,
                        "stdout": "hello\n",
                    }
                },
            }
        },
    }
    out = render_event(event)
    assert out is not None
    assert "[tool ✓]" in out
    assert "exit=0" in out
    assert "1 lines" in out


def test_render_tool_call_unknown_tool_falls_back() -> None:
    event = {
        "type": "tool_call",
        "subtype": "started",
        "tool_call": {"futureToolCall": {"args": {}, "description": "do thing"}},
    }
    out = render_event(event)
    assert out is not None
    assert "futureToolCall" in out
    assert "do thing" in out


def test_render_result_success() -> None:
    event = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 9541,
        "usage": {"inputTokens": 3, "outputTokens": 5},
    }
    out = render_event(event)
    assert out is not None
    assert "9541ms" in out
    assert "in=3" in out
    assert "out=5" in out


def test_render_result_error() -> None:
    event = {
        "type": "result",
        "is_error": True,
        "result": "boom",
    }
    out = render_event(event)
    assert out is not None
    assert "error" in out
    assert "boom" in out


def test_render_unknown_event_type_returns_marker() -> None:
    out = render_event({"type": "future_event_type_we_dont_know"})
    assert out is not None
    assert "[unknown:future_event_type_we_dont_know]" in out


def test_render_thinking_non_delta_event() -> None:
    # Non-delta thinking events (no timestamp_ms) still render as a
    # standalone line via render_event.
    event = {
        "type": "thinking",
        "message": {"content": [{"type": "text", "text": "let me consider..."}]},
    }
    out = render_event(event)
    assert out is not None
    assert "[thinking]" in out
    assert "let me consider" in out


def test_render_thinking_delta_suppressed_in_render_event() -> None:
    # Delta thinking events are coalesced by the streaming caller via
    # classify_delta, so render_event must not emit them as their own
    # lines (otherwise each token becomes a separate `[thinking] ...` line).
    event = {
        "type": "thinking",
        "subtype": "delta",
        "text": "Let",
        "timestamp_ms": 1,
    }
    assert render_event(event) is None


def test_classify_delta_assistant() -> None:
    event = {
        "type": "assistant",
        "timestamp_ms": 1,
        "message": {"content": [{"type": "text", "text": "hi"}]},
    }
    assert classify_delta(event) == ("assistant", "hi")


def test_classify_delta_thinking_text_field() -> None:
    # cursor-agent emits thinking deltas with a top-level ``text`` field.
    event = {
        "type": "thinking",
        "subtype": "delta",
        "text": " me read",
        "timestamp_ms": 2,
    }
    assert classify_delta(event) == ("thinking", " me read")


def test_classify_delta_non_delta_returns_none() -> None:
    assert classify_delta({"type": "system"}) is None
    non_delta_assistant = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "x"}]},
    }
    assert classify_delta(non_delta_assistant) is None


def test_delta_stream_prefix_and_suffix() -> None:
    assert "[thinking]" in delta_stream_prefix("thinking")
    assert delta_stream_prefix("assistant") == ""
    assert delta_stream_suffix("thinking") != ""
    assert delta_stream_suffix("assistant") == ""


def test_render_assistant_with_no_text_returns_none() -> None:
    event = {
        "type": "assistant",
        "timestamp_ms": 1,
        "message": {"content": []},
    }
    assert render_event(event) is None
