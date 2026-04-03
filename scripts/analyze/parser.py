"""Re-exports from the canonical observatory parser.

All shared dataclasses and parsing functions live in
scripts/observatory/data/parser.py. This module re-exports them so that
analyze-pipeline scripts can import from a single location without changing
their import paths.

The only addition here is extract_tool_sequence, which is specific to the
analyze pipeline.
"""
from __future__ import annotations

from scripts.observatory.data.parser import (
    ApiCall,
    TokenUsage,
    ToolCall,
    ToolResult,
    TranscriptFile,
    deduplicate_api_calls,
    discover_transcripts,
    parse_session,
)

__all__ = [
    "ApiCall",
    "TokenUsage",
    "ToolCall",
    "ToolResult",
    "TranscriptFile",
    "deduplicate_api_calls",
    "discover_transcripts",
    "extract_tool_sequence",
    "parse_session",
]


def extract_tool_sequence(api_calls: list[ApiCall]) -> list[ToolCall]:
    """Flatten all tool calls from api_calls in order."""
    return [tc for call in api_calls for tc in call.tool_calls]
