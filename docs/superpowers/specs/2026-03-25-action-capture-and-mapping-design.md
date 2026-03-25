# Action Capture & Mapping Pipeline — Design Spec

## Overview

Build the first milestone of the dd-cc-setup observability pipeline: capture all Claude Code tool calls, classify them by category/plugin, evaluate routing rules, and log rich JSONL entries for downstream analysis.

> **Note**: This spec creates the initial `config/mappings.json` schema. Per project rules, future schema changes require updating the categorisation script in tandem.

## Decisions Made

| Question | Answer |
|----------|--------|
| Events to capture | Both PreToolUse and PostToolUse |
| Routing trigger | Tool name + optional input inspection (hybrid) |
| Routing decisions | `pass`, `soft_deny`, `deny` (observation is always-on, not a state) |
| Handler style | Code-driven — config points to Python functions |
| Config location | Single file `config/mappings.json` |
| Scope | Scripts only — no hook wiring yet |

## Config Schema: `config/mappings.json`

```json
{
  "_version": "1.0",
  "_fallback": { "category": "unknown", "plugin": "unknown", "decision": "pass" },

  "tools": {
    "Read": { "category": "file_ops", "plugin": "core" },
    "Bash": { "category": "bash_exec", "plugin": "core" },
    "mcp__jcodemunch__search_symbols": { "category": "code_search", "plugin": "jcodemunch" }
  },

  "mcp_prefixes": {
    "mcp__jcodemunch__": { "category": "code_search", "plugin": "jcodemunch" },
    "mcp__jdocmunch__":  { "category": "doc_read",    "plugin": "jdocmunch" }
  },

  "routing": [
    {
      "matcher": { "tool": "Read", "input_key": "file_path", "pattern": ".*\\.(py|js|ts|go|java|kt)$" },
      "decision": "soft_deny",
      "handler": "scripts.routing.handlers.route_read_code"
    },
    {
      "matcher": { "tool": "Read", "input_key": "file_path", "pattern": ".*\\.(md|rst|txt)$" },
      "decision": "soft_deny",
      "handler": "scripts.routing.handlers.route_read_doc"
    },
    {
      "matcher": { "tool": "WebSearch" },
      "decision": "deny",
      "handler": "scripts.routing.handlers.redirect_to_exa"
    }
  ]
}
```

### Lookup logic

1. **Classification**: exact match in `tools` → prefix match in `mcp_prefixes` → `_fallback`
2. **Routing**: iterate `routing` list, first match wins. No match → `_fallback.decision` (pass)
3. **Matcher fields**: `tool` (required), `input_key` + `pattern` (optional regex on tool_input)

## JSONL Entry Schema

Each log line written by `logger.py`:

```json
{
  "ts": 1774459459,
  "event_type": "PreToolUse",
  "tool_name": "Read",
  "category": "file_ops",
  "plugin": "core",
  "args": { "file_path": "/src/app.py" },
  "input_size": 42,
  "decision": "soft_deny",
  "handler": "scripts.routing.handlers.route_read_code",
  "handler_output": { "redirect_to": "mcp__jcodemunch__get_file_content", "reason": "Use jCodeMunch for .py files" },
  "latency_ms": 12,
  "session_id": "abc-123"
}
```

### Field sources

| Field | Source | Notes |
|-------|--------|-------|
| `ts` | `int(time.time())` | Unix epoch in seconds (int), matches existing hook-events.jsonl |
| `event_type` | stdin `hook_event_name` | PreToolUse / PostToolUse |
| `tool_name` | stdin `tool_name` | Raw tool name |
| `category` | mappings.json lookup | Resolved via tools → mcp_prefixes → fallback |
| `plugin` | mappings.json lookup | Same resolution chain |
| `args` | stdin `tool_input` | Full tool input dict |
| `input_size` | `len(json.dumps(args))` | Byte count proxy for token estimation (not actual tokens) |
| `decision` | routing evaluation | pass / soft_deny / deny |
| `handler` | routing match | Python handler path, or null if pass |
| `handler_output` | handler return value | What the handler returned, or null |
| `latency_ms` | timer | Script execution time in ms |
| `session_id` | stdin `session_id` | Optional; null if hook event omits it |

## Project Structure

```
config/
  mappings.json          — tools + mcp_prefixes + routing rules

scripts/
  capture/
    __init__.py          — (exists)
    logger.py            — orchestrator: capture + classify + route-evaluate + JSONL write
  categorise/
    __init__.py          — (exists)
    classifier.py        — lookup: tools → mcp_prefixes → fallback
    router.py            — iterate routing rules, first-match-wins evaluation
  routing/
    __init__.py
    handlers.py          — handler function stubs (populated later with reference material)

tests/
  test_capture_logger.py
  test_classifier.py
  test_router.py
```

### Module responsibilities

- **`classifier.py`** — pure lookup, returns `{category, plugin}` for any tool name
- **`router.py`** — evaluates routing rules against `(tool_name, tool_input)`, returns `{decision, handler, handler_output}`. Uses Python `re` module for pattern matching (compiled + cached). Invalid regex falls back to no-match.
- **`logger.py`** — orchestrates: reads stdin → classifies → routes → builds entry → appends JSONL. Always exits 0 (fail-open, pure observability). Hook enforcement (exit codes, deny JSON) is a separate concern.
- **`handlers.py`** — stubs only for now; real routing logic added later with reference material. Handler contract: `handler(tool_name: str, tool_input: dict) -> dict | None`. Returns a dict (logged as `handler_output`) or None. Exceptions are caught by router and logged; decision still recorded.

### Call flow

```
stdin JSON
  → logger.main()
    → classifier.classify(tool_name, mappings) → {category, plugin}
    → router.evaluate(tool_name, tool_input, routing_rules) → {decision, handler, handler_output}
    → build_entry(event, classification, routing_result)
    → append_entry(log_path, entry)
  → exit 0 (always)
```

### Config loading

`_fallback` is required in `config/mappings.json`. If missing, code defaults to `{category: "unknown", plugin: "unknown", decision: "pass"}`.

### Log path

`CC_ACTION_LOG` env var, default `~/.claude/logs/actions.jsonl`.

## Data Sources for Mapping Population

During implementation, dispatch parallel subagents to extract tool→category→routing data from these sources:

| Source | Path | Extracts |
|--------|------|----------|
| RTK | `~/Repos/rtk/README.md` + `~/Repos/rtk/src/*.rs` | All supported bash command rewrites; which commands RTK handles |
| jCodeMunch | `~/Repos/jcodemunch-mcp/AGENT_HOOKS.md`, `USER_GUIDE.md`, `ARCHITECTURE.md` | When to use each jCodeMunch tool; Read→jCodeMunch routing rules |
| jDocMunch | `~/Repos/jdocmunch-mcp/ARCHITECTURE.md`, `README.md`, `USER_GUIDE.md` | When to use each jDocMunch tool; Read→jDocMunch routing rules |
| context-mode | `~/Repos/context-mode/configs/claude-code/CLAUDE.md`, `README.md` | When to use ctx_execute/ctx_execute_file; Bash→context-mode routing rules |

### Extraction strategy

1. Launch 4 parallel subagents (one per source), each returns structured JSON: `{tool_name, category, plugin, routing_decision, handler_description}`
2. Merge results in main context
3. Identify overlaps (tools claimed by multiple sources) → write to `config/overlaps.json` for manual resolution
4. Populate `config/mappings.json` tools, mcp_prefixes, and routing sections

## Out of Scope

- Hook wiring in `.claude/settings.local.json`
- Real handler implementations (stubs return pass)
- PostToolUse-specific logic (token savings tracking — future task)
- Hook enforcement (exit codes, deny JSON responses)
