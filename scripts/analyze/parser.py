"""Transcript discovery and parsing for task 1.4 baseline mining.

Discovers ~/.claude/projects/*/*.jsonl files, parses them into ApiCall
dataclasses with deduplication of streaming chunks, tool call extraction,
and tool result correlation.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptFile:
    """A discovered transcript JSONL file."""

    path: Path
    session_id: str
    is_subagent: bool
    agent_id: str | None
    agent_type: str | None


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation from an assistant message."""

    name: str
    tool_use_id: str
    input: dict  # type: ignore[type-arg]
    file_path: str | None
    file_ext: str | None


@dataclass(frozen=True)
class ToolResult:
    """A tool result from a user message, correlated by tool_use_id."""

    tool_use_id: str
    content_length: int | None


@dataclass(frozen=True)
class TokenUsage:
    """Token usage from message.usage."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


@dataclass(frozen=True)
class ApiCall:
    """A deduplicated API call (final streaming chunk only)."""

    request_id: str
    session_id: str
    agent_id: str | None
    permission_mode: str | None
    stop_reason: str | None
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    usage: TokenUsage


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_transcripts(base_dir: Path) -> list[TranscriptFile]:
    """Walk base_dir/*/  finding *.jsonl files and subagent subdirectories.

    Reads .meta.json for agentType when present.
    """
    results: list[TranscriptFile] = []

    if not base_dir.is_dir():
        return results

    for project_dir in base_dir.iterdir():
        if not project_dir.is_dir():
            continue
        # Top-level session files in the project dir
        for jsonl_file in project_dir.glob("*.jsonl"):
            results.append(
                TranscriptFile(
                    path=jsonl_file,
                    session_id=jsonl_file.stem,
                    is_subagent=False,
                    agent_id=None,
                    agent_type=None,
                )
            )
        # Subagent subdirectories
        for sub_dir in project_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            agent_type = _read_agent_type(sub_dir)
            for jsonl_file in sub_dir.glob("*.jsonl"):
                results.append(
                    TranscriptFile(
                        path=jsonl_file,
                        session_id=jsonl_file.stem,
                        is_subagent=True,
                        agent_id=sub_dir.name,
                        agent_type=agent_type,
                    )
                )

    return results


def _read_agent_type(directory: Path) -> str | None:
    """Read agentType from .meta.json in a directory, or return None."""
    meta = directory / ".meta.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data.get("agentType")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_session(path: Path) -> Iterator[dict]:  # type: ignore[type-arg]
    """Yield parsed JSONL lines for assistant and user entries only.

    Skips malformed lines (logs a warning). Never raises.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON at %s line %d — skipped", path, lineno)
                    continue
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") not in ("assistant", "user"):
                    continue
                yield entry
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def deduplicate_api_calls(
    entries: Iterable[dict],  # type: ignore[type-arg]
    session_id: str,
    agent_id: str | None = None,
) -> list[ApiCall]:
    """Group assistant entries by requestId; keep the final streaming chunk.

    Also extracts ToolResult from the following user entries by correlating
    tool_use_id. Extracts permission_mode from the most recent preceding user
    entry for each request group.

    Streaming dedup rule:
    - Final chunk = entry where stop_reason is not None.
    - If multiple final chunks, pick highest output_tokens.
    - Orphan partials (all stop_reason=None) → skip + warn.
    """
    # Collect entries in order, tracking last seen permission_mode and pending
    # tool_results per request group.
    #
    # We need to correlate user entries (tool_results) with the preceding
    # assistant request. Strategy: after we see an assistant entry with
    # tool_use blocks, the *next* user entry contains the tool_results.

    # Two-pass within the entry list:
    # 1. Group all assistant entries by requestId.
    # 2. For each group, find the following user entry to get tool_results and
    #    the preceding user entry for permission_mode.

    entry_list = list(entries)

    # Map requestId → list of (index, entry) for assistant entries
    groups: dict[str, list[tuple[int, dict]]] = {}  # type: ignore[type-arg]
    # Track permission_mode at each index (from user entries)
    perm_at_index: dict[int, str] = {}

    for idx, entry in enumerate(entry_list):
        if entry.get("type") == "user":
            mode = entry.get("permissionMode")
            if mode:
                perm_at_index[idx] = mode
        elif entry.get("type") == "assistant":
            req_id = entry.get("requestId", "")
            if req_id not in groups:
                groups[req_id] = []
            groups[req_id].append((idx, entry))

    # For each requestId group, select the final chunk
    calls: list[ApiCall] = []

    for req_id, indexed_entries in groups.items():
        # Find final chunk(s)
        finals = [
            (idx, e)
            for idx, e in indexed_entries
            if _get_stop_reason(e) is not None
        ]

        if not finals:
            logger.warning("Orphan partial stream for requestId=%s — skipped", req_id)
            continue

        # Pick highest output_tokens among finals
        final_idx, final_entry = max(
            finals, key=lambda ie: _get_output_tokens(ie[1])
        )

        # Find permission_mode: last user entry strictly before final_idx
        permission_mode: str | None = None
        for idx in range(final_idx - 1, -1, -1):
            if idx in perm_at_index:
                permission_mode = perm_at_index[idx]
                break

        # Extract tool calls from assistant message content
        tool_calls = _extract_tool_calls(final_entry)

        # Extract tool results from the first user entry after final_idx
        tool_results: tuple[ToolResult, ...] = ()
        for idx in range(final_idx + 1, len(entry_list)):
            if entry_list[idx].get("type") == "user":
                tool_results = _extract_tool_results(entry_list[idx])
                break

        usage = _extract_usage(final_entry)
        stop_reason = _get_stop_reason(final_entry)

        calls.append(
            ApiCall(
                request_id=req_id,
                session_id=session_id,
                agent_id=agent_id,
                permission_mode=permission_mode,
                stop_reason=stop_reason,
                tool_calls=tool_calls,
                tool_results=tool_results,
                usage=usage,
            )
        )

    return calls


def _get_stop_reason(entry: dict) -> str | None:  # type: ignore[type-arg]
    return entry.get("message", {}).get("stop_reason")


def _get_output_tokens(entry: dict) -> int:  # type: ignore[type-arg]
    return entry.get("message", {}).get("usage", {}).get("output_tokens", 0)


def _extract_tool_calls(entry: dict) -> tuple[ToolCall, ...]:  # type: ignore[type-arg]
    content = entry.get("message", {}).get("content", [])
    result = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        name = block.get("name", "")
        tool_use_id = block.get("id", "")
        inp = block.get("input", {})
        file_path = inp.get("file_path") if isinstance(inp, dict) else None
        file_ext = os.path.splitext(file_path)[1] if file_path else None
        result.append(
            ToolCall(
                name=name,
                tool_use_id=tool_use_id,
                input=inp,
                file_path=file_path,
                file_ext=file_ext or None,
            )
        )
    return tuple(result)


def _extract_tool_results(entry: dict) -> tuple[ToolResult, ...]:  # type: ignore[type-arg]
    content = entry.get("message", {}).get("content", [])
    result = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue
        tool_use_id = block.get("tool_use_id", "")
        raw_content = block.get("content")
        if raw_content is None:
            content_length = None
        elif isinstance(raw_content, str):
            content_length = len(raw_content)
        elif isinstance(raw_content, list):
            # Content may be a list of blocks; sum text lengths
            content_length = sum(
                len(b.get("text", ""))
                for b in raw_content
                if isinstance(b, dict)
            )
        else:
            content_length = None
        result.append(ToolResult(tool_use_id=tool_use_id, content_length=content_length))
    return tuple(result)


def _extract_usage(entry: dict) -> TokenUsage:  # type: ignore[type-arg]
    usage = entry.get("message", {}).get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
        cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
    )


# ---------------------------------------------------------------------------
# Tool sequence extraction
# ---------------------------------------------------------------------------


def extract_tool_sequence(api_calls: list[ApiCall]) -> list[ToolCall]:
    """Flatten all tool calls from api_calls in order."""
    return [tc for call in api_calls for tc in call.tool_calls]
