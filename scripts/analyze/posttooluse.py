"""R6: PostToolUse/cron reindex savings analysis.

Measures token savings achievable by offloading index refresh to PostToolUse
hooks, eliminating deny→reindex chains from the transcript record.

All extraction functions operate on deduplicated ApiCall objects (via
deduplicate_api_calls) to avoid streaming chunk double-counting.

Depends on empirical findings:
- R5: reindex chain cost mean=511 tok (R5_MEAN_CHAIN_COST)
- R6b: 47% of index calls are reactive (22% post-deny, 25% post-ToolSearch)
- R3: ToolSearch detour cost mean=293 tok (R3_MEAN_DETOUR_COST)
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.analyze.parser import ApiCall, ToolCall

# ---------------------------------------------------------------------------
# Empirical constants (from prior research tasks)
# ---------------------------------------------------------------------------

R5_MEAN_CHAIN_COST = 511   # tok: mean deny→reindex chain cost (R5)
R3_MEAN_DETOUR_COST = 293  # tok: mean ToolSearch detour cost (R3, Read-specific)

# Tools that trigger PostToolUse reindexing
WRITE_EDIT_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})

# Index tool name fragments (MCP tool names contain these)
INDEX_TOOL_FRAGMENTS = ("index_folder", "index_local")

# Deny detection text patterns (checked when is_error flag may be absent)
DENY_PATTERNS = ("blocked", "denied this tool", "hook error", "no stderr output")

# Bash file creation command patterns
BASH_FILE_CREATE_PATTERNS = ("tee ", "cat >", "> /", "touch ", ">> ")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DenyEvent:
    """A tool call that was denied (error response in tool_result)."""

    session_id: str
    tool_name: str
    tool_use_id: str
    error_text: str
    output_tokens: int  # Claude's wasted generation (deduplicated)


@dataclass(frozen=True)
class IndexCall:
    """An index_folder or index_local call with trigger classification."""

    session_id: str
    tool_name: str         # contains "index_folder" or "index_local"
    trigger: str           # "post_deny" | "post_toolsearch" | "other"
    chain_cost_tokens: int  # output_tokens from triggering deny through this call


@dataclass(frozen=True)
class WriteEditEvent:
    """A Write, Edit, or MultiEdit tool call (PostToolUse trigger candidate)."""

    session_id: str
    tool_name: str   # "Write" | "Edit" | "MultiEdit"
    file_path: str | None
    file_ext: str | None


@dataclass(frozen=True)
class R6Result:
    """Counterfactual savings from PostToolUse reindexing."""

    # Direct savings: post-deny chains eliminated entirely
    post_deny_index_chains: int
    post_deny_tokens_saved: int
    # Indirect savings at sensitivity range (25%/50%/75% elimination)
    post_toolsearch_index_chains: int
    indirect_savings_low: int
    indirect_savings_mid: int
    indirect_savings_high: int
    # Write activity: PostToolUse trigger volume
    write_edit_count: int         # Write + Edit + MultiEdit
    writes_per_session: float
    # Coverage gap: file mutations not covered by PostToolUse
    bash_file_creation_count: int
    coverage_gap_pct: float       # bash_creates / (write_edit + bash_creates)


# ---------------------------------------------------------------------------
# Error map construction
# ---------------------------------------------------------------------------


def build_error_map(entries: list[dict]) -> dict[str, tuple[bool, str]]:  # type: ignore[type-arg]
    """Build tool_use_id → (is_error, error_text) from raw user entries.

    Must be called before deduplicate_api_calls. Preserves the is_error flag
    that ToolResult dataclass does not capture.

    Detection strategy:
    1. is_error=True in the block → deny
    2. Error text matches a DENY_PATTERN → deny (handles hook crashes that
       omit the is_error flag)
    """
    result: dict[str, tuple[bool, str]] = {}
    for entry in entries:
        if entry.get("type") != "user":
            continue
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id", "")
            if not tool_use_id:
                continue
            is_error = bool(block.get("is_error", False))
            raw = block.get("content", "")
            if isinstance(raw, str):
                error_text = raw
            elif isinstance(raw, list):
                error_text = " ".join(
                    b.get("text", "") for b in raw if isinstance(b, dict)
                )
            else:
                error_text = ""
            # Upgrade to deny if text matches a known pattern
            if not is_error and any(p in error_text.lower() for p in DENY_PATTERNS):
                is_error = True
            result[tool_use_id] = (is_error, error_text)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_deny(api_call: ApiCall, error_map: dict[str, tuple[bool, str]]) -> bool:
    """True if any tool_result in this ApiCall is a deny."""
    return any(
        error_map.get(tr.tool_use_id, (False, ""))[0]
        for tr in api_call.tool_results
    )


def _is_index_tool(tc: ToolCall) -> bool:
    return any(frag in tc.name for frag in INDEX_TOOL_FRAGMENTS)


def _is_toolsearch(tc: ToolCall) -> bool:
    return tc.name == "ToolSearch"


def _has_bash_file_creation(tc: ToolCall) -> bool:
    if tc.name != "Bash":
        return False
    cmd = (tc.input.get("command") or "")
    return any(p in cmd for p in BASH_FILE_CREATE_PATTERNS)


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------


def extract_deny_events(
    api_calls: list[ApiCall],
    error_map: dict[str, tuple[bool, str]],
    session_id: str,
) -> list[DenyEvent]:
    """Extract deny events from deduplicated ApiCalls.

    Joins ApiCall.tool_results with error_map to find denied tool calls.
    output_tokens is taken from the deduplicated ApiCall (no double-counting).
    """
    events: list[DenyEvent] = []
    for call in api_calls:
        # Build id → ToolCall lookup for name resolution
        tc_by_id = {tc.tool_use_id: tc for tc in call.tool_calls}
        for tr in call.tool_results:
            entry = error_map.get(tr.tool_use_id)
            if not (entry and entry[0]):
                continue
            tc = tc_by_id.get(tr.tool_use_id)
            tool_name = tc.name if tc else "unknown"
            events.append(
                DenyEvent(
                    session_id=session_id,
                    tool_name=tool_name,
                    tool_use_id=tr.tool_use_id,
                    error_text=entry[1],
                    output_tokens=call.usage.output_tokens,
                )
            )
    return events


def extract_index_calls(
    api_calls: list[ApiCall],
    error_map: dict[str, tuple[bool, str]],
    session_id: str,
    lookback: int = 3,
) -> list[IndexCall]:
    """Extract index calls with trigger classification.

    Classifies each index_folder/index_local call by the context of the
    preceding `lookback` ApiCalls:
    - "post_deny": a deny event is within lookback window (deny wins)
    - "post_toolsearch": a ToolSearch call is within lookback window
    - "other": no matching context

    chain_cost_tokens = sum of output_tokens from triggering deny through
    the index call (deduplicated, no double-counting).
    """
    result: list[IndexCall] = []
    for i, call in enumerate(api_calls):
        for tc in call.tool_calls:
            if not _is_index_tool(tc):
                continue
            preceding = api_calls[max(0, i - lookback) : i]
            trigger = "other"
            chain_cost = call.usage.output_tokens
            # Scan from most recent backward; deny takes priority
            deny_idx: int | None = None
            ts_found = False
            for j, prior in enumerate(reversed(preceding)):
                abs_idx = i - 1 - j
                if _is_deny(prior, error_map):
                    trigger = "post_deny"
                    deny_idx = abs_idx
                    break
                if any(_is_toolsearch(t) for t in prior.tool_calls):
                    ts_found = True
                    # Keep scanning for a deny that overrides
            if trigger == "other" and ts_found:
                trigger = "post_toolsearch"
            # Compute chain cost from deny call through index call
            if deny_idx is not None:
                chain_cost = sum(
                    c.usage.output_tokens for c in api_calls[deny_idx : i + 1]
                )
            result.append(
                IndexCall(
                    session_id=session_id,
                    tool_name=tc.name,
                    trigger=trigger,
                    chain_cost_tokens=chain_cost,
                )
            )
    return result


def extract_write_edit_events(
    api_calls: list[ApiCall],
    session_id: str,
) -> tuple[list[WriteEditEvent], int]:
    """Extract Write/Edit/MultiEdit events and Bash file creation count.

    Returns (write_edit_events, bash_file_creation_count).

    bash_file_creation_count represents the coverage gap: file mutations
    via Bash that PostToolUse:Write+Edit+MultiEdit would not trigger on.
    """
    events: list[WriteEditEvent] = []
    bash_creates = 0
    for call in api_calls:
        for tc in call.tool_calls:
            if tc.name in WRITE_EDIT_TOOLS:
                events.append(
                    WriteEditEvent(
                        session_id=session_id,
                        tool_name=tc.name,
                        file_path=tc.file_path,
                        file_ext=tc.file_ext,
                    )
                )
            elif _has_bash_file_creation(tc):
                bash_creates += 1
    return events, bash_creates


# ---------------------------------------------------------------------------
# Counterfactual computation
# ---------------------------------------------------------------------------


def compute_counterfactual(
    index_calls: list[IndexCall],
    write_edit_events: list[WriteEditEvent],
    bash_creates: int,
    session_count: int,
) -> R6Result:
    """Compute counterfactual token savings from PostToolUse reindexing.

    PostToolUse cost is NOT subtracted: hooks execute outside the model
    context window (shell/Python scripts calling MCP directly). From the
    model's perspective, PostToolUse reindexing costs zero tokens.

    Indirect savings are a sensitivity range (25%/50%/75% elimination)
    since the true elimination fraction is not empirically measured.
    """
    post_deny = [c for c in index_calls if c.trigger == "post_deny"]
    post_toolsearch = [c for c in index_calls if c.trigger == "post_toolsearch"]

    direct_savings = len(post_deny) * R5_MEAN_CHAIN_COST

    pts = len(post_toolsearch)
    indirect_low = int(pts * 0.25 * R3_MEAN_DETOUR_COST)
    indirect_mid = int(pts * 0.50 * R3_MEAN_DETOUR_COST)
    indirect_high = int(pts * 0.75 * R3_MEAN_DETOUR_COST)

    we_count = len(write_edit_events)
    writes_per_session = we_count / session_count if session_count > 0 else 0.0

    total_mutations = we_count + bash_creates
    coverage_gap = bash_creates / total_mutations if total_mutations > 0 else 0.0

    return R6Result(
        post_deny_index_chains=len(post_deny),
        post_deny_tokens_saved=direct_savings,
        post_toolsearch_index_chains=pts,
        indirect_savings_low=indirect_low,
        indirect_savings_mid=indirect_mid,
        indirect_savings_high=indirect_high,
        write_edit_count=we_count,
        writes_per_session=writes_per_session,
        bash_file_creation_count=bash_creates,
        coverage_gap_pct=coverage_gap,
    )
