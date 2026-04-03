"""
Data structures for the observability pipeline.

Four structures:
  HookInput       — immutable, from Claude stdin
  PipelineContext — mutable dict (plain dict, not a class), flows between steps
  ObservationEntry — JSONL projection (plain dict, built by build_observation_entry)
  HookResponse    — immutable, returned to Claude
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from scripts.redact import redact_tool_input


@dataclass(frozen=True)
class HookInput:
    session_id: str
    tool_use_id: str
    tool_name: str
    tool_input: dict
    hook_event_name: str
    cwd: str
    transcript_path: str
    permission_mode: str
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: object) -> HookInput:
        if not isinstance(data, dict):
            raise TypeError(f"HookInput.from_dict expects a dict, got {type(data).__name__}")
        known = {
            "session_id", "tool_use_id", "tool_name", "tool_input",
            "hook_event_name", "cwd", "transcript_path", "permission_mode",
        }
        raw = {k: v for k, v in data.items() if k not in known}
        return cls(
            session_id=data.get("session_id", ""),
            tool_use_id=data.get("tool_use_id", ""),
            tool_name=data.get("tool_name", ""),
            tool_input=data.get("tool_input", {}),
            hook_event_name=data.get("hook_event_name", ""),
            cwd=data.get("cwd", ""),
            transcript_path=data.get("transcript_path", ""),
            permission_mode=data.get("permission_mode", ""),
            raw=raw,
        )


@dataclass(frozen=True)
class HookResponse:
    exit_code: int  # 0 = pass, 1 = soft_deny, 2 = hard_deny
    stderr_message: str = ""


def build_initial_context(hook_input: HookInput) -> dict:
    """Seed PipelineContext from a parsed HookInput.

    Sets all decision factors to None (Phase 1 — transcript-based factors deferred to 1.6).
    Sets decision to 'pass' (fail-open default).
    """
    return {
        "session_id": hook_input.session_id,
        "tool_use_id": hook_input.tool_use_id,
        "tool_name": hook_input.tool_name,
        "tool_input": hook_input.tool_input,
        "hook_event_name": hook_input.hook_event_name,
        "cwd": hook_input.cwd,
        "transcript_path": hook_input.transcript_path,
        "permission_mode": hook_input.permission_mode,
        # Decision factors — stubbed None in Phase 1 (task 1.6 implements transcript tailing)
        "previous_tool": None,
        "is_retry": None,
        "file_ext": None,
        "file_size": None,
        "index_fresh": None,  # PHASE_1_STUB: always None — check_*_index_fresh always defaults True
        # Pipeline state
        "matcher_id": None,
        "category": None,
        "decision": "pass",
        "redirect_to": None,
        "steps_trace": [],
        "errors": [],
        "warnings": [],
    }


def build_observation_entry(context: dict, start_time: float) -> dict:
    """Project PipelineContext to an ObservationEntry dict for JSONL logging.

    event_type priority: error > pass_through > fallback > decision
    latency_ms: wall time from start_time to now.
    """
    latency_ms = int((time.time() - start_time) * 1000)

    if context.get("errors"):
        event_type = "error"
    elif context.get("_pass_through"):
        event_type = "pass_through"
    elif context.get("matcher_id") is None:
        event_type = "fallback"
    else:
        event_type = "decision"

    return {
        "ts": int(time.time()),
        "event_type": event_type,
        "tool_use_id": context.get("tool_use_id", ""),
        "session_id": context.get("session_id", ""),
        "tool_name": context.get("tool_name", ""),
        "tool_input": redact_tool_input(
            context.get("tool_name", ""), context.get("tool_input", {})
        ),
        "hook_event_name": context.get("hook_event_name", ""),
        "matcher_id": context.get("matcher_id"),
        "category": context.get("category"),
        "decision": context.get("decision", "pass"),
        "redirect_to": context.get("redirect_to"),
        "decision_factors": {
            "previous_tool": context.get("previous_tool"),
            "is_retry": context.get("is_retry"),
            "file_ext": context.get("file_ext"),
            "file_size": context.get("file_size"),
            "index_fresh": context.get("index_fresh"),
        },
        "errors": context.get("errors", []),
        "warnings": context.get("warnings", []),
        "steps_trace": context.get("steps_trace", []),
        "latency_ms": latency_ms,
    }


def build_hook_response(context: dict) -> HookResponse:
    """Build HookResponse. Phase 1: always exit 0 (observe-only, no enforcement)."""
    return HookResponse(
        exit_code=0,
        stderr_message=context.get("_stderr_message", ""),
    )
