"""Tests for scripts.engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.engine as engine


def _hook_payload(**overrides) -> dict:
    base = {
        "session_id": "sess-1",
        "tool_use_id": "tu-1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/app.py"},
        "hook_event_name": "PreToolUse",
        "cwd": "/project",
        "transcript_path": "/tmp/transcript.json",
        "permission_mode": "default",
    }
    base.update(overrides)
    return base


def _mappings() -> dict:
    return {
        "_fallback": {"decision": "pass"},
        "_pass_through": ["Edit"],
        "_mcp_pass_through_prefixes": ["mcp__"],
        "Read": {
            "matchers": [
                {
                    "id": "read_code_file",
                    "method": "matchers.is_code_file",
                    "category": "code_ops",
                    "observe": {"enabled": True, "level": "debug"},
                    "steps": [
                        {"type": "transform", "method": "steps.enrich_file_metadata"},
                        {"type": "decide", "method": "steps.soft_deny_redirect"},
                        {"type": "resolve", "method": "steps.format_deny_message"},
                    ],
                }
            ]
        },
    }


def _disabled_observe_mappings() -> dict:
    mappings = _mappings()
    mappings["Read"]["matchers"][0]["observe"]["enabled"] = False
    return mappings


def test_parse_stdin_parses_hook_payload():
    hook_input = engine.parse_stdin(json.dumps(_hook_payload()))
    assert hook_input.tool_name == "Read"
    assert hook_input.tool_use_id == "tu-1"


def test_load_mappings_reads_json(tmp_path: Path):
    path = tmp_path / "mappings.json"
    path.write_text(json.dumps({"_fallback": {"decision": "pass"}}))
    assert engine.load_mappings(path)["_fallback"]["decision"] == "pass"


def test_run_pipeline_marks_pass_through():
    context = {"tool_name": "Edit", "tool_input": {}}
    result, matcher = engine.run_pipeline(context, _mappings())
    assert result["_pass_through"] is True
    assert matcher is None


def test_run_pipeline_marks_mcp_pass_through():
    context = {"tool_name": "mcp__jcodemunch__get_file_content", "tool_input": {}}
    result, matcher = engine.run_pipeline(context, _mappings())
    assert result["_pass_through"] is True
    assert matcher is None


def test_run_pipeline_executes_first_matching_pipeline(tmp_path: Path):
    file_path = tmp_path / "app.py"
    file_path.write_text("print('hello')\n")
    context = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(file_path)},
        "decision": "pass",
        "steps_trace": [],
        "errors": [],
    }
    result, matcher = engine.run_pipeline(context, _mappings())
    assert matcher["id"] == "read_code_file"
    assert result["matcher_id"] == "read_code_file"
    assert result["category"] == "code_ops"
    assert result["decision"] == "soft_deny"
    assert result["redirect_to"] == "mcp__jcodemunch__get_file_content"
    assert len(result["steps_trace"]) == 3


def test_run_pipeline_uses_fallback_when_no_matcher():
    context = {"tool_name": "Bash", "tool_input": {}, "decision": "hard_deny"}
    result, matcher = engine.run_pipeline(context, _mappings())
    assert matcher is None
    assert result["decision"] == "pass"


def test_should_log_respects_observe_enabled():
    assert engine.should_log({"observe": {"enabled": False}}) is False
    assert engine.should_log({"observe": {"enabled": True}}) is True
    assert engine.should_log(None) is True


def test_main_logs_and_returns_zero(tmp_path: Path):
    file_path = tmp_path / "app.py"
    file_path.write_text("print('hello')\n")
    payload = json.dumps(_hook_payload(tool_input={"file_path": str(file_path)}))

    with patch("scripts.engine.load_mappings", return_value=_mappings()), patch(
        "scripts.engine.write_log"
    ) as write_log:
        exit_code = engine.main(payload)

    assert exit_code == 0
    write_log.assert_called_once()


def test_main_fail_open_logs_error_on_parse_failure():
    with patch("scripts.engine.write_error_log") as write_error_log:
        exit_code = engine.main("{invalid json")
    assert exit_code == 0
    write_error_log.assert_called_once()


def test_main_skips_write_log_when_observe_disabled(tmp_path: Path):
    file_path = tmp_path / "app.py"
    file_path.write_text("print('hello')\n")
    payload = json.dumps(_hook_payload(tool_input={"file_path": str(file_path)}))

    with patch("scripts.engine.load_mappings", return_value=_disabled_observe_mappings()), patch(
        "scripts.engine.write_log"
    ) as write_log:
        exit_code = engine.main(payload)

    assert exit_code == 0
    write_log.assert_not_called()


def test_load_mappings_real_config():
    """Load the actual config/mappings.json and verify version."""
    from pathlib import Path
    config_path = Path(__file__).parent.parent / "config" / "mappings.json"
    result = engine.load_mappings(config_path)
    assert result["_version"] == "2.0"


def test_load_mappings_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.load_mappings(tmp_path / "nonexistent.json")


def test_resolve_callable_resolves_matcher():
    fn = engine.resolve_callable("matchers.is_code_file")
    assert callable(fn)
    # verify it actually works
    assert fn({"tool_input": {"file_path": "/tmp/app.py"}}) is True


def test_resolve_callable_resolves_step():
    fn = engine.resolve_callable("steps.soft_deny_redirect")
    assert callable(fn)


def test_resolve_callable_raises_on_unknown_function():
    with pytest.raises(AttributeError):
        engine.resolve_callable("matchers.nonexistent_function_xyz")


def test_routing_tools_not_pass_through():
    """Read, Bash, Glob, Grep are NOT pass-through — they fall through to matchers."""
    # With an empty matchers mapping, they fall to fallback (decision=pass)
    # but are NOT marked _pass_through
    minimal_mappings = {
        "_fallback": {"decision": "pass"},
        "_pass_through": [],
        "_mcp_pass_through_prefixes": [],
    }
    for tool in ["Read", "Bash", "Glob", "Grep"]:
        ctx = {"tool_name": tool, "tool_input": {}}
        result, matcher = engine.run_pipeline(ctx, minimal_mappings)
        assert (
            result.get("_pass_through") is not True
        ), f"{tool} should not be pass-through"


def test_run_pipeline_unknown_tool_falls_to_fallback():
    ctx = {"tool_name": "Agent", "tool_input": {}}
    result, matcher = engine.run_pipeline(ctx, _mappings())
    assert result["decision"] == "pass"
    assert matcher is None


def test_run_pipeline_steps_trace_empty_at_info_level(tmp_path):
    # Create mappings with level=info (not debug)
    path = tmp_path / "app.py"
    path.write_text("x = 1\n")
    mappings = _mappings()
    mappings["Read"]["matchers"][0]["observe"]["level"] = "info"
    ctx = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(path)},
        "decision": "pass",
        "steps_trace": [],
        "errors": [],
    }
    result, _ = engine.run_pipeline(ctx, mappings)
    assert result["steps_trace"] == []


def test_run_pipeline_abort_on_check_failure():
    """Check step with on_failure=abort + index_fresh=False → fallback to pass."""
    abort_mappings = {
        "_fallback": {"decision": "pass"},
        "_pass_through": [],
        "_mcp_pass_through_prefixes": [],
        "Read": {
            "matchers": [
                {
                    "id": "abort_test",
                    "method": "matchers.always",
                    "category": "test",
                    "observe": {"enabled": True, "level": "info"},
                    "steps": [
                        {
                            "type": "check",
                            "method": "steps.check_code_index_fresh",
                            "on_failure": "abort",
                        },
                    ],
                }
            ]
        },
    }
    ctx = {
        "tool_name": "Read",
        "tool_input": {},
        "index_fresh": False,
        "decision": "pass",
        "steps_trace": [],
        "errors": [],
    }
    result, _ = engine.run_pipeline(ctx, abort_mappings)
    assert result["decision"] == "pass"


def test_run_pipeline_observe_disabled_sets_flag(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("x = 1\n")
    mappings = _mappings()
    mappings["Read"]["matchers"][0]["observe"]["enabled"] = False
    ctx = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(path)},
        "decision": "pass",
        "steps_trace": [],
        "errors": [],
    }
    # should_log is called externally with the returned matcher
    result, matcher = engine.run_pipeline(ctx, mappings)
    assert engine.should_log(matcher) is False


def test_run_pipeline_observe_enabled_true_by_default(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("x = 1\n")
    mappings = _mappings()
    # Remove observe key entirely
    del mappings["Read"]["matchers"][0]["observe"]
    ctx = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(path)},
        "decision": "pass",
        "steps_trace": [],
        "errors": [],
    }
    result, matcher = engine.run_pipeline(ctx, mappings)
    assert engine.should_log(matcher) is True


def test_main_crash_guard_logs_error_entry(tmp_path):
    """Mid-pipeline RuntimeError → event_type='error' written to log."""
    payload = json.dumps(_hook_payload())

    with patch(
        "scripts.engine.load_mappings",
        side_effect=RuntimeError("test crash error"),
    ), patch("scripts.engine.write_log") as write_log, patch(
        "scripts.engine.write_error_log"
    ) as write_error_log:
        exit_code = engine.main(payload)

    assert exit_code == 0
    # Either write_log or write_error_log captures the crash
    assert write_log.called or write_error_log.called
    if write_log.called:
        entry = write_log.call_args[0][0]
        assert "test crash error" in str(entry.get("errors", []))


def test_main_populates_transcript_factors(tmp_path: Path):
    """Transcript factors are resolved and appear in the logged observation entry."""
    import json as _json

    # Write a transcript with a completed Edit call
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        _json.dumps({
            "type": "assistant",
            "requestId": "req-prev",
            "message": {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "tool_use", "id": "tu-0", "name": "Edit",
                     "input": {"file_path": "/src/app.py"}}
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }) + "\n"
    )

    payload = json.dumps(_hook_payload(transcript_path=str(transcript)))

    with patch("scripts.engine.write_log") as write_log, patch(
        "scripts.engine.write_error_log"
    ):
        engine.main(payload)

    assert write_log.called
    entry = write_log.call_args[0][0]
    factors = entry.get("decision_factors", {})
    assert factors["previous_tool"] == "Edit"
    assert factors["is_retry"] is False
