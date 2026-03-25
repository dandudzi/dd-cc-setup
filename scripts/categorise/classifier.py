"""Classifier for categorizing Claude Code tool calls.

This module provides the `classify` function which resolves tool names to
category and plugin using a priority-based resolution chain.

Resolution chain:
1. Exact match in mappings["tools"]
2. Longest matching prefix in mappings["mcp_prefixes"]
3. Fallback to mappings["_fallback"]
4. Hardcoded default if _fallback missing
"""

type MappingsDict = dict[str, dict]
type ClassificationResult = dict[str, str]


def _extract(entry: dict) -> ClassificationResult:
    """Extract category and plugin from a mapping entry with safe defaults.

    Args:
        entry: A mapping entry dict with optional "category" and "plugin" keys.

    Returns:
        A dict with "category" and "plugin" keys, using "unknown" as defaults.
    """
    return {
        "category": entry.get("category", "unknown"),
        "plugin": entry.get("plugin", "unknown"),
    }


def classify(tool_name: str, mappings: MappingsDict) -> ClassificationResult:
    """Classify a tool call by name using configured mappings.

    Args:
        tool_name: The name of the tool to classify.
        mappings: A dictionary with keys "tools", "mcp_prefixes", and optionally "_fallback".

    Returns:
        A dict with "category" and "plugin" keys.

    Raises:
        TypeError: If tool_name is not a string or mappings is not a dict.
    """
    if not isinstance(tool_name, str):
        raise TypeError(f"tool_name must be a string, got {type(tool_name).__name__}")

    if not isinstance(mappings, dict):
        raise TypeError(f"mappings must be a dict, got {type(mappings).__name__}")

    # 1. Check for exact match in tools
    tools = mappings.get("tools")
    if isinstance(tools, dict) and tool_name in tools:
        entry = tools[tool_name]
        return _extract(entry)

    # 2. Check for longest matching prefix in mcp_prefixes
    mcp_prefixes = mappings.get("mcp_prefixes")
    if isinstance(mcp_prefixes, dict):
        matching_prefixes = [
            prefix
            for prefix in mcp_prefixes
            if tool_name.startswith(prefix)
        ]
        if matching_prefixes:
            # Use the longest matching prefix
            longest_prefix = max(matching_prefixes, key=len)
            entry = mcp_prefixes[longest_prefix]
            return _extract(entry)

    # 3. Use _fallback if available
    fallback = mappings.get("_fallback")
    if isinstance(fallback, dict):
        return _extract(fallback)

    # 4. Hardcoded default
    return {"category": "unknown", "plugin": "unknown"}
