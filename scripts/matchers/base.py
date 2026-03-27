"""
Base matcher interface and built-in matchers.

A matcher is a callable:

    matcher(context: dict) -> bool

`context` contains at minimum:
  - tool_name (str): the Claude Code tool being called
  - tool_input (dict): the raw input arguments for the tool call
  - session (dict): session-level state (index freshness, previous_tool, is_retry, etc.)

Matchers must be pure functions — no side effects, no I/O.
The engine imports them by dotted name from config/mappings.json.

Phase 1 will implement: is_code_file, is_doc_file, is_large_data_file,
is_unbounded_bash, always, and any tool-specific matchers.
"""
