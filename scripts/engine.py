"""Observability pipeline engine for Claude Code hook events.

NOTE: Must be invoked as a module to resolve package-absolute imports:
    uv run python -m scripts.engine
Running as a script (python scripts/engine.py) raises ModuleNotFoundError.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

from scripts.models import (
    HookInput,
    build_hook_response,
    build_initial_context,
    build_observation_entry,
)
from scripts.observe.logger import write_error_log, write_log
from scripts.transcript import enrich_transcript_factors

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "mappings.json"


def parse_stdin(stdin_text: str | None = None) -> HookInput:
    """Parse Claude hook stdin into HookInput."""
    payload = sys.stdin.read() if stdin_text is None else stdin_text
    data = json.loads(payload or "{}")
    return HookInput.from_dict(data)


def load_mappings(path: Path = CONFIG_PATH) -> dict:
    """Load the v2.0 routing config."""
    with path.open() as handle:
        return json.load(handle)


def resolve_callable(dotted_name: str):
    """Resolve config method references like `matchers.is_code_file`."""
    module_name, attr_name = dotted_name.rsplit(".", 1)
    if module_name == "matchers":
        module_name = "scripts.matchers"
    elif module_name == "steps":
        module_name = "scripts.steps"

    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def should_log(matcher_config: dict | None) -> bool:
    """Return whether the current matcher should emit a JSONL entry."""
    if matcher_config is None:
        return True
    observe = matcher_config.get("observe", {})
    return observe.get("enabled", True)


def _record_step_trace(context: dict, step_config: dict, observe_level: str) -> dict:
    if observe_level != "debug":
        return context

    trace = list(context.get("steps_trace", []))
    trace.append(
        {
            "type": step_config.get("type"),
            "method": step_config.get("method"),
            "decision": context.get("decision"),
            "redirect_to": context.get("redirect_to"),
        }
    )
    updated = dict(context)
    updated["steps_trace"] = trace
    return updated


def _apply_fallback(context: dict, mappings: dict) -> dict:
    updated = dict(context)
    updated["decision"] = mappings.get("_fallback", {}).get("decision", "pass")
    updated["matcher_id"] = None
    updated["category"] = None
    updated["redirect_to"] = None
    updated["steps_trace"] = []
    return updated


def _run_steps(context: dict, matcher_config: dict) -> tuple[dict, bool]:
    observe_level = matcher_config.get("observe", {}).get("level", "info")
    current = dict(context)

    for step_config in matcher_config.get("steps", []):
        step = resolve_callable(step_config["method"])
        current = step(current)
        current = _record_step_trace(current, step_config, observe_level)

        if (
            step_config.get("type") == "check"
            and current.get("index_fresh") is False
            and step_config.get("on_failure", "abort") == "abort"
        ):
            return current, True

    if observe_level != "debug":
        current["steps_trace"] = []

    return current, False


def run_pipeline(context: dict, mappings: dict) -> tuple[dict, dict | None]:
    """Apply pass-through checks, matcher selection, and step execution."""
    tool_name = context.get("tool_name", "")

    if tool_name in mappings.get("_pass_through", []):
        updated = dict(context)
        updated["_pass_through"] = True
        return updated, None

    prefixes = mappings.get("_mcp_pass_through_prefixes", [])
    if any(tool_name.startswith(prefix) for prefix in prefixes):
        updated = dict(context)
        updated["_pass_through"] = True
        return updated, None

    tool_config = mappings.get(tool_name)
    if tool_config is None:
        return _apply_fallback(context, mappings), None

    for matcher_config in tool_config.get("matchers", []):
        matcher = resolve_callable(matcher_config["method"])
        if not matcher(context):
            continue

        current = dict(context)
        current["matcher_id"] = matcher_config.get("id")
        current["category"] = matcher_config.get("category")
        current, aborted = _run_steps(current, matcher_config)
        if aborted:
            return _apply_fallback(current, mappings), matcher_config
        return current, matcher_config

    return _apply_fallback(context, mappings), None


def emit_response(context: dict) -> int:
    """Emit the hook response and return the process exit code."""
    response = build_hook_response(context)
    if response.stderr_message:
        print(response.stderr_message, file=sys.stderr)
    return response.exit_code


def main(stdin_text: str | None = None) -> int:
    """Run the engine with a fail-open crash guard."""
    start = time.time()
    context: dict = {}
    matcher_config: dict | None = None
    should_write_log = True

    try:
        hook_input = parse_stdin(stdin_text)
        context = build_initial_context(hook_input)
        context = enrich_transcript_factors(context)  # task 1.6
        mappings = load_mappings()
        context, matcher_config = run_pipeline(context, mappings)
        should_write_log = should_log(matcher_config)
    except Exception as exc:
        if context:
            errors = list(context.get("errors", []))
            errors.append(str(exc))
            context["errors"] = errors
            context["decision"] = "pass"
        else:
            write_error_log("", str(exc))
            return 0
    finally:
        if context and should_write_log:
            entry = build_observation_entry(context, start)
            if matcher_config and matcher_config.get("observe", {}).get("level") != "debug":
                entry["steps_trace"] = []
            write_log(entry)

    return emit_response(context)


if __name__ == "__main__":
    sys.exit(main())
