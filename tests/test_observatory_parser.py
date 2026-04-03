"""Tests for scripts/observatory/data/parser.py — structural hardening (Finding #4)."""
from __future__ import annotations

import pytest

from scripts.observatory.data.parser import deduplicate_api_calls


def _assistant_entry(request_id: str = "req-1", **overrides) -> dict:
    """Minimal valid assistant entry with a stop_reason."""
    base: dict = {
        "type": "assistant",
        "requestId": request_id,
        "message": {
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            "content": [],
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Malformed message field
# ---------------------------------------------------------------------------

class TestMalformedMessage:
    def test_message_none_does_not_crash(self):
        """Entry with message=None should be skipped, not crash."""
        entry = _assistant_entry(message=None)
        result = deduplicate_api_calls([entry], session_id="sess-1")
        # Should return empty list (no valid finals)
        assert isinstance(result, list)

    def test_message_string_does_not_crash(self):
        """Entry with message='string' should be skipped, not crash."""
        entry = _assistant_entry(message="unexpected string")
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert isinstance(result, list)

    def test_message_int_does_not_crash(self):
        """Entry with message=42 should be skipped, not crash."""
        entry = _assistant_entry(message=42)
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Malformed content field
# ---------------------------------------------------------------------------

class TestMalformedContent:
    def test_content_int_does_not_crash(self):
        """Entry with content=42 (non-iterable) should produce empty tool_calls."""
        entry = _assistant_entry(message={
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "content": 42,
        })
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].tool_calls == ()

    def test_content_dict_not_list_does_not_crash(self):
        """Entry with content={} (dict not list) should produce empty tool_calls."""
        entry = _assistant_entry(message={
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "content": {"unexpected": "dict"},
        })
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].tool_calls == ()


# ---------------------------------------------------------------------------
# Malformed usage field
# ---------------------------------------------------------------------------

class TestMalformedUsage:
    def test_usage_int_does_not_crash(self):
        """Entry with usage=42 should produce zero-filled TokenUsage."""
        entry = _assistant_entry(message={
            "stop_reason": "end_turn",
            "usage": 42,
            "content": [],
        })
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].usage.input_tokens == 0
        assert result[0].usage.output_tokens == 0

    def test_usage_none_does_not_crash(self):
        """Entry with usage=None should produce zero-filled TokenUsage."""
        entry = _assistant_entry(message={
            "stop_reason": "end_turn",
            "usage": None,
            "content": [],
        })
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].usage.input_tokens == 0

    def test_usage_string_does_not_crash(self):
        """Entry with usage='bad' should produce zero-filled TokenUsage."""
        entry = _assistant_entry(message={
            "stop_reason": "end_turn",
            "usage": "bad",
            "content": [],
        })
        result = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].usage.input_tokens == 0


# ---------------------------------------------------------------------------
# Malformed tool result content in user entry
# ---------------------------------------------------------------------------

class TestMalformedToolResultContent:
    def test_user_entry_content_int_does_not_crash(self):
        """User entry with content=42 should produce empty tool_results."""
        assistant = _assistant_entry()
        user_entry = {
            "type": "user",
            "message": {"content": 42},
        }
        result = deduplicate_api_calls([assistant, user_entry], session_id="sess-1")
        assert len(result) == 1
        assert result[0].tool_results == ()
