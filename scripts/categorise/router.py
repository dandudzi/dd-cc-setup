"""Router module — evaluates routing rules against tool calls.

The router matches tool calls against rules from the routing configuration,
making decisions about whether to allow, deny, or redirect the call through
a handler function.

Public API:
    evaluate(tool_name, tool_input, routing_rules) -> dict

Returns a dict with structure:
    {
        "decision": str,           # "pass", "soft_deny", "deny"
        "handler": str | None,     # handler path or None
        "handler_output": dict | None  # handler return value or None
    }
"""

import importlib
import re
from typing import Any

# Module-level regex cache: maps pattern string -> compiled Pattern or None
_pattern_cache: dict[str, re.Pattern[str] | None] = {}


def _get_or_compile_pattern(pattern: str) -> re.Pattern[str] | None:
    """Get cached compiled pattern, or compile and cache it.

    Args:
        pattern: Regex pattern string.

    Returns:
        Compiled re.Pattern object, or None if pattern is invalid.
    """
    if pattern not in _pattern_cache:
        try:
            _pattern_cache[pattern] = re.compile(pattern)
        except re.error:
            # Invalid regex — cache None to avoid recompiling
            _pattern_cache[pattern] = None
    return _pattern_cache[pattern]


def _matches_rule(tool_name: str, tool_input: dict, matcher: dict) -> bool:
    """Check if a tool call matches a routing rule matcher.

    Args:
        tool_name: Name of the tool being called.
        tool_input: Input dict passed to the tool.
        matcher: Matcher dict from routing rule with structure:
            {
                "tool": "Read",
                "input_key": "file_path" (optional),
                "pattern": ".*\\.py$" (optional, requires input_key)
            }

    Returns:
        True if tool call matches the matcher, False otherwise.
    """
    # Tool name must match exactly
    if matcher.get("tool") != tool_name:
        return False

    # If no input_key, tool name match is sufficient
    if "input_key" not in matcher:
        return True

    # Tool name matched and input_key is specified
    input_key = matcher["input_key"]

    # If input_key is missing from tool_input, no match
    if input_key not in tool_input:
        return False

    # If pattern is not specified, input_key presence is sufficient
    if "pattern" not in matcher:
        return True

    # Pattern is specified — try to match
    pattern = matcher["pattern"]
    compiled_pattern = _get_or_compile_pattern(pattern)

    # If pattern is invalid, treat as no-match
    if compiled_pattern is None:
        return False

    # Check if pattern matches the input value
    input_value = tool_input[input_key]
    return bool(compiled_pattern.search(str(input_value)))


def _call_handler(
    handler_path: str,
    tool_name: str,
    tool_input: dict,
) -> dict | None:
    """Dynamically import and call a handler function.

    Args:
        handler_path: Dotted path like "scripts.routing.handlers.route_read_code".
        tool_name: Name of the tool being called.
        tool_input: Input dict passed to the tool.

    Returns:
        Handler return value (dict or None), or None if handler raises exception.
    """
    try:
        # Split module path from function name
        module_path, func_name = handler_path.rsplit(".", 1)

        # Dynamically import module
        module = importlib.import_module(module_path)

        # Get handler function
        handler_func = getattr(module, func_name)

        # Call handler with tool_name and tool_input
        return handler_func(tool_name, tool_input)
    except Exception:
        # Any exception is caught — handler_output will be None
        return None


def evaluate(
    tool_name: str,
    tool_input: dict,
    routing_rules: list[dict],
) -> dict[str, Any]:
    """Evaluate routing rules against a tool call.

    Iterates through rules in order, returning the first matching rule's
    decision, handler path, and handler output. If no rule matches,
    returns pass decision.

    Args:
        tool_name: Name of the tool being called.
        tool_input: Input dict passed to the tool.
        routing_rules: List of routing rule dicts, each with:
            {
                "matcher": { "tool": str, "input_key": str (opt), "pattern": str (opt) },
                "decision": str,
                "handler": str | None
            }

    Returns:
        Dict with structure:
            {
                "decision": str,              # "pass", "soft_deny", "deny"
                "handler": str | None,        # handler path or None
                "handler_output": dict | None # handler return value or None
            }
    """
    # Iterate through rules — first match wins
    for rule in routing_rules:
        matcher = rule.get("matcher", {})

        if _matches_rule(tool_name, tool_input, matcher):
            # Rule matched
            decision = rule.get("decision", "pass")
            handler_path = rule.get("handler")
            handler_output = None

            # If handler is specified, call it
            if handler_path:
                handler_output = _call_handler(handler_path, tool_name, tool_input)

            return {
                "decision": decision,
                "handler": handler_path,
                "handler_output": handler_output,
            }

    # No rule matched — return pass
    return {
        "decision": "pass",
        "handler": None,
        "handler_output": None,
    }
