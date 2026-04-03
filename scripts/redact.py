"""Redaction of sensitive payloads in logs.

Provides per-tool allowlists to drop sensitive keys (secrets, tokens, passwords)
from tool_input before logging to JSONL.
"""


def redact_tool_input(tool_name: str, tool_input) -> dict:
    """Redact sensitive keys from tool_input dict based on tool-specific rules.

    Args:
        tool_name: Name of the tool (e.g., "Read", "Bash", "Write").
        tool_input: The tool input dict (or None, list, etc.).

    Returns:
        A new dict with sensitive keys removed. Returns {} if input is not a dict.

    Per-tool allowlists (keys to keep):
      - Read: file_path
      - Write: file_path
      - Edit: file_path
      - Bash: command (truncated at 80 chars if longer)
      - Glob: pattern, path
      - Grep: pattern, path, glob, type
      - WebSearch: query
      - WebFetch: url
      - Default: all keys except those with 'token', 'key', 'secret', 'password',
                 'credential', 'auth' in their lowercase name
    """
    # Validate input is a dict
    if not isinstance(tool_input, dict):
        return {}

    # Tool-specific allowlists
    if tool_name == "Read":
        return _keep_keys(tool_input, {"file_path"})
    elif tool_name == "Write":
        return _keep_keys(tool_input, {"file_path"})
    elif tool_name == "Edit":
        return _keep_keys(tool_input, {"file_path"})
    elif tool_name == "Bash":
        return _redact_bash(tool_input)
    elif tool_name == "Glob":
        return _keep_keys(tool_input, {"pattern", "path"})
    elif tool_name == "Grep":
        return _keep_keys(tool_input, {"pattern", "path", "glob", "type"})
    elif tool_name == "WebSearch":
        return _keep_keys(tool_input, {"query"})
    elif tool_name == "WebFetch":
        return _keep_keys(tool_input, {"url"})
    else:
        # Default: drop sensitive key names, keep others
        return _drop_sensitive_keys(tool_input)


def _keep_keys(input_dict: dict, allowed: set) -> dict:
    """Return a new dict with only allowed keys."""
    return {k: v for k, v in input_dict.items() if k in allowed}


def _drop_sensitive_keys(input_dict: dict) -> dict:
    """Return a new dict, dropping keys with sensitive names.

    Drops keys whose lowercase name contains: token, key, secret, password,
    credential, auth.
    """
    sensitive_keywords = {"token", "key", "secret", "password", "credential", "auth"}
    result = {}
    for k, v in input_dict.items():
        k_lower = k.lower()
        # Check if any sensitive keyword is a substring of the lowercase key name
        if not any(keyword in k_lower for keyword in sensitive_keywords):
            result[k] = v
    return result


def _redact_bash(input_dict: dict) -> dict:
    """Redact Bash tool input: keep command (truncated at 80), drop sensitive keys."""
    result = {}
    for k, v in input_dict.items():
        k_lower = k.lower()
        # Drop sensitive key names (same as _drop_sensitive_keys)
        sensitive_keywords = {"token", "key", "secret", "password", "credential", "auth", "env"}
        if any(keyword in k_lower for keyword in sensitive_keywords):
            continue
        # For 'command' key: truncate if longer than 80 chars
        if k == "command" and isinstance(v, str):
            if len(v) > 80:
                result[k] = v[:80] + "...[truncated]"
            else:
                result[k] = v
        else:
            result[k] = v
    return result
