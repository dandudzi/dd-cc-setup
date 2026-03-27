"""Tests for scripts/models.py — four data structures for the pipeline."""
import time

import pytest

from scripts.models import (
    HookInput,
    build_hook_response,
    build_initial_context,
    build_observation_entry,
)


def _hook_input(**overrides) -> dict:
    """Minimal valid HookInput source dict."""
    base = {
        "session_id": "sess-1",
        "tool_use_id": "tu-1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/src/app.py"},
        "hook_event_name": "PreToolUse",
        "cwd": "/project",
        "transcript_path": "/tmp/t.json",
        "permission_mode": "default",
    }
    base.update(overrides)
    return base


def _context(**overrides) -> dict:
    """Minimal valid PipelineContext for projection tests."""
    base = {
        "session_id": "sess-1",
        "tool_use_id": "tu-1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/src/app.py"},
        "hook_event_name": "PreToolUse",
        "cwd": "/project",
        "transcript_path": "/tmp/t.json",
        "permission_mode": "default",
        "previous_tool": None,
        "is_retry": None,
        "file_ext": None,
        "file_size": None,
        "index_fresh": None,
        "matcher_id": None,
        "category": None,
        "decision": "pass",
        "redirect_to": None,
        "steps_trace": [],
        "errors": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


class TestHookInput:
    def test_from_dict_maps_all_known_fields(self):
        hi = HookInput.from_dict(_hook_input())
        assert hi.session_id == "sess-1"
        assert hi.tool_use_id == "tu-1"
        assert hi.tool_name == "Read"
        assert hi.tool_input == {"file_path": "/src/app.py"}
        assert hi.hook_event_name == "PreToolUse"
        assert hi.cwd == "/project"
        assert hi.transcript_path == "/tmp/t.json"
        assert hi.permission_mode == "default"

    def test_from_dict_unknown_fields_go_to_raw(self):
        hi = HookInput.from_dict(_hook_input(future_field="xyz"))
        assert hi.raw["future_field"] == "xyz"
        assert "future_field" not in hi.__dataclass_fields__

    def test_from_dict_missing_fields_default_to_empty(self):
        hi = HookInput.from_dict({})
        assert hi.session_id == ""
        assert hi.tool_name == ""
        assert hi.tool_input == {}
        assert hi.raw == {}

    def test_hookinput_is_immutable(self):
        hi = HookInput.from_dict(_hook_input())
        with pytest.raises((AttributeError, TypeError)):
            hi.tool_name = "Write"

    def test_from_dict_raises_typeerror_for_list(self):
        with pytest.raises(TypeError, match="expects a dict"):
            HookInput.from_dict([])

    def test_from_dict_raises_typeerror_for_string(self):
        with pytest.raises(TypeError, match="expects a dict"):
            HookInput.from_dict("x")

    def test_from_dict_raises_typeerror_for_int(self):
        with pytest.raises(TypeError, match="expects a dict"):
            HookInput.from_dict(1)

    def test_from_dict_raises_typeerror_for_none(self):
        with pytest.raises(TypeError, match="expects a dict"):
            HookInput.from_dict(None)


class TestBuildInitialContext:
    def test_all_hookinput_fields_propagated(self):
        hi = HookInput.from_dict(_hook_input())
        ctx = build_initial_context(hi)
        assert ctx["session_id"] == "sess-1"
        assert ctx["tool_name"] == "Read"
        assert ctx["tool_input"] == {"file_path": "/src/app.py"}
        assert ctx["cwd"] == "/project"
        assert ctx["transcript_path"] == "/tmp/t.json"

    def test_decision_factors_stubbed_none(self):
        ctx = build_initial_context(HookInput.from_dict(_hook_input()))
        assert ctx["previous_tool"] is None
        assert ctx["is_retry"] is None
        assert ctx["file_ext"] is None
        assert ctx["file_size"] is None
        assert ctx["index_fresh"] is None

    def test_pipeline_state_initialized(self):
        ctx = build_initial_context(HookInput.from_dict(_hook_input()))
        assert ctx["decision"] == "pass"
        assert ctx["matcher_id"] is None
        assert ctx["category"] is None
        assert ctx["redirect_to"] is None
        assert ctx["steps_trace"] == []
        assert ctx["errors"] == []

    def test_returns_plain_dict(self):
        ctx = build_initial_context(HookInput.from_dict(_hook_input()))
        assert isinstance(ctx, dict)


class TestBuildObservationEntry:
    def test_event_type_decision_when_matcher_fired(self):
        ctx = _context(matcher_id="read_code_file", decision="soft_deny")
        entry = build_observation_entry(ctx, time.time())
        assert entry["event_type"] == "decision"

    def test_event_type_fallback_when_no_matcher(self):
        ctx = _context(matcher_id=None, decision="pass")
        entry = build_observation_entry(ctx, time.time())
        assert entry["event_type"] == "fallback"

    def test_event_type_error_when_errors_present(self):
        ctx = _context(errors=["boom"])
        entry = build_observation_entry(ctx, time.time())
        assert entry["event_type"] == "error"

    def test_event_type_pass_through_flag(self):
        ctx = _context(_pass_through=True)
        entry = build_observation_entry(ctx, time.time())
        assert entry["event_type"] == "pass_through"

    def test_has_all_required_top_level_fields(self):
        entry = build_observation_entry(_context(), time.time())
        required = [
            "ts", "event_type", "tool_use_id", "session_id", "tool_name",
            "tool_input", "hook_event_name", "matcher_id", "category",
            "decision", "redirect_to", "decision_factors", "errors",
            "steps_trace", "latency_ms",
        ]
        for field in required:
            assert field in entry, f"Missing: {field}"

    def test_decision_factors_envelope_has_all_keys(self):
        ctx = _context(file_ext=".py", file_size=1000)
        entry = build_observation_entry(ctx, time.time())
        df = entry["decision_factors"]
        assert df["file_ext"] == ".py"
        assert df["file_size"] == 1000
        assert df["previous_tool"] is None
        assert df["is_retry"] is None
        assert df["index_fresh"] is None

    def test_latency_ms_positive(self):
        entry = build_observation_entry(_context(), time.time() - 0.05)
        assert entry["latency_ms"] >= 0

    def test_ts_is_unix_int(self):
        entry = build_observation_entry(_context(), time.time())
        assert isinstance(entry["ts"], int)
        assert abs(entry["ts"] - int(time.time())) <= 2

    def test_steps_trace_excluded_at_info_level(self):
        ctx = _context(steps_trace=[])
        entry = build_observation_entry(ctx, time.time())
        assert entry["steps_trace"] == []


class TestBuildObservationEntryWarnings:
    def test_stat_warning_does_not_set_error_event_type(self):
        """Warnings (like stat failures) should not override event_type to 'error'."""
        ctx = _context(
            matcher_id="read_code_file",
            decision="soft_deny",
            warnings=["unable to stat file: /missing.py"],
            errors=[],  # No errors, only warnings
        )
        entry = build_observation_entry(ctx, time.time())
        assert entry["event_type"] == "decision", "warnings should not set event_type=error"
        assert "warnings" in entry, "warnings should be present in output"
        assert entry["warnings"] == ["unable to stat file: /missing.py"]

    def test_warnings_included_in_observation_entry(self):
        """Warnings field should be included in the output dict."""
        ctx = _context(warnings=["warning 1", "warning 2"])
        entry = build_observation_entry(ctx, time.time())
        assert entry["warnings"] == ["warning 1", "warning 2"]

    def test_warnings_default_to_empty_list(self):
        """If no warnings present, should default to empty list."""
        ctx = _context()  # No warnings set
        entry = build_observation_entry(ctx, time.time())
        assert entry["warnings"] == []


class TestBuildHookResponse:
    def test_phase1_always_exits_zero(self):
        for decision in ("pass", "soft_deny", "hard_deny"):
            ctx = _context(decision=decision)
            resp = build_hook_response(ctx)
            assert resp.exit_code == 0, f"Expected 0 for decision={decision}"

    def test_stderr_message_from_context(self):
        ctx = _context(_stderr_message="Use jCodeMunch instead")
        resp = build_hook_response(ctx)
        assert resp.stderr_message == "Use jCodeMunch instead"

    def test_stderr_empty_by_default(self):
        resp = build_hook_response(_context())
        assert resp.stderr_message == ""

    def test_hookresponse_is_immutable(self):
        resp = build_hook_response(_context())
        with pytest.raises((AttributeError, TypeError)):
            resp.exit_code = 1
