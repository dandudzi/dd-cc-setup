"""Tests for scripts.engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts import engine


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
