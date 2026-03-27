# dd-cc-setup

## Rules to follow

- Check `todo.md` before starting each step — it is the **source of truth** for progress
- **Phase 1 (Observability) in progress.** Tasks 1.1/1.2 complete (pipeline live). Remaining: 1.3, 1.4, 1.5b, 1.6. Phase 0 complete.
- All plans must be written to files in `docs/plans/` and each plan **must link back** to its corresponding step in `todo.md` (e.g., `See: todo.md step 1.2`)
- Every step in `todo.md` that produces a plan must link forward to that plan file (e.g., `Plan: docs/plans/001-hook-routing.md`)
- When completing a todo step, mark it done in `todo.md` immediately

## Project Purpose

A token-reduction system for Claude Code, built on observability and intelligent hook routing.

The project defines a complete Claude Code setup that:
1. **Categorizes** every Claude Code action (tool call) through a extensible decision framework
2. **Routes** actions via hooks to token-efficient tools (jDocMunch, jCodeMunch, RTK, context-mode, and future additions)
3. **Observes** every decision — what was routed, where, how much was saved, what was missed
4. **Deploys** as a portable system usable across multiple projects

The core idea: hooks intercept Claude's tool calls, categorize them against a JSON-based multi-level mapping, make a routing decision, and log the outcome. Observability is a byproduct of the decision system itself — if a call flows through the hooks, it's automatically observed and measured.

**Phase 0 redesigned this from scratch.** New architecture: per-tool pipeline with configurable matcher+step chains. Config is routing metadata only; logic lives in Python methods.

## Tech Stack

- Language: Python 3.12+
- Package manager: uv
- Linting/formatting: ruff
- Testing: pytest
- Log format: JSONL (one JSON object per line)

## Deployment

## Coding Rules

- Comment complex logic
- Always use TDD skill for coding
- Use semantic commits
- No hardcoded secrets or paths — use config files

## Don't Change

- Architectural decisions (unless explicitly requested)
- `config/mappings.json` v2.0 schema without updating `scripts/engine.py` to match

## Reference Docs

- `config/mappings.json` — v2.0 schema: tool → matchers[] → steps[] (routing metadata only)
- `scripts/engine.py` — pipeline walker: parse stdin → match → run steps → log → emit response
- `scripts/models.py` — HookInput, HookResponse, build_initial_context(), build_observation_entry(), build_hook_response()
- `scripts/observe/logger.py` — write_log(), write_error_log(); logs to `~/.claude/logs/actions.jsonl`
- `scripts/matchers/base.py` — matcher interface: `(context: dict) -> bool`
- `scripts/steps/base.py` — step interface: `(context: dict) -> dict`, 4 types: check / transform / decide / resolve
- `docs/plans/009-phase0-synthesis.md` — complete Phase 0 findings and all decisions
- `docs/superpowers/specs/2026-03-27-observability-pipeline-design.md` — Phase 1 design spec (authoritative)
- `docs/` — architecture notes and findings

## Tool Source Repos (local checkouts — use these as source of truth)

All tools used in this project are checked out locally. **Always verify tool capabilities against these repos directly** — do not infer from hooks or mappings.json.

| Tool         | Local Path                | Key docs                                                                                 | Intent / When to use                                                                                                                                                                                                           |
| ------------ | ------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| jDocMunch    | `~/Repos/jdocmunch-mcp/`  | README.md, USER_GUIDE.md, SPEC.md, ARCHITECTURE.md                                       | Index and retrieve **documentation** files (.md, .rst, .txt) by heading hierarchy. Use instead of Read for any doc file. Primary tool for searching project docs, specs, guides.                                               |
| jCodeMunch   | `~/Repos/jcodemunch-mcp/` | README.md, USER_GUIDE.md, SPEC.md, CONFIGURATION.md, LANGUAGE_SUPPORT.md, AGENT_HOOKS.md | Index and retrieve **source code** by symbol (function, class, method). Use instead of Read for code files. Enables sliced reads — fetch only the symbol needed, not the whole file.                                           |
| RTK          | `~/Repos/rtk/`            | README.md, ARCHITECTURE.md, docs/                                                        | **Bash command optimizer**. Rewrites verbose shell commands into token-efficient equivalents. Never blocks; runs as a passthrough rewriter before Bash executes. Use for any shell operation.                                  |
| context-mode | `~/Repos/context-mode/`   | README.md, docs/, llms.txt, llms-full.txt                                                | **Large-output sandbox**. Runs commands, processes files, and fetches URLs inside a sandbox so raw output never floods the context window. Use for Bash commands producing >20 lines, data files >100 lines, and web fetching. |

When spawning agents to research tool behaviour, point them at these paths. Use jDocMunch MCP to index and search them — do not raw-read large files.

## Hook Decision Types

Three decision types used across all hooks in this project:

| Type          | Exit Code          | Behaviour                                                                                                                                                 | Example                                            |
| ------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| **HARD_DENY** | `exit 2`           | Tool completely blocked. No retry, no fallback suggested. Claude receives an error and must choose a different tool.                                      | `webfetch-block.sh`, `websearch-block.sh`          |
| **SOFT_DENY** | `exit 1` + message | Tool blocked this time, but hook outputs a suggestion. A second attempt is often permitted (session-gate pattern). Claude gets guidance, not just a wall. | `unified-read-router.sh`, `jmunch-session-gate.sh` |
| **PASS**      | `exit 0`           | Tool proceeds normally. Includes passive/observe hooks that never block, RTK allow-list fast-exit, and gate checks when index is fresh.                   | `grep-observe.sh`, `observe.sh`, RTK allow-list    |

> **Phase 1 note:** `scripts/engine.py` always exits 0 regardless of decision type (observe-only mode). Exit codes 1 and 2 are Phase 2+ enforcement behavior. The engine logs decisions but does not block tools in Phase 1.

**Session-gate retry pattern (SOFT_DENY variant):** `jmunch-session-gate.sh` blocks the first Read call if the jCodeMunch/jDocMunch index is not fresh, then allows a second attempt after the index is rebuilt. This is intentional — it forces an index refresh rather than permanently denying the tool.

## Task Management

- Use TaskCreate for multi-step work
- Set dependencies with addBlockedBy for sequential phases
- Update status to in_progress before starting each task
- Mark completed only after verification

## What We Know (Phase 0 findings)

**Decision priority order** (highest wins):
1. **Intent** — `previous_tool = Edit/Write` → always PASS (modification mode needs raw content)
2. **Data type** — file extension → routes to jCodeMunch / jDocMunch / neither
3. **Volume** — output/file size → routes to context-mode if large
4. **Index availability** — index stale → SOFT_DENY to force refresh
5. **is_retry** — same tool + same input as prior call → always PASS (loop-breaker)

**Intent is transcript-based** (not /tmp sentinels):
- `previous_tool`: tail the session transcript (~1ms) to find the last tool called
- `is_retry`: same tool + same `tool_input` as previous call → loop-break, always PASS

**Tools are orthogonal axes** (D0.11):
- jCodeMunch / jDocMunch = data type (what KIND of content)
- context-mode = volume (how MUCH output)
- RTK = command pattern (Bash rewrite only, post-decision transform — never a routing decision)

**jCodeMunch and jDocMunch are MCP-only** — no shell CLI for indexing/search. Hooks cannot call them directly. Routing pattern: `exit 1` + message (`"Use mcp__jcodemunch__... instead"`).

**RTK is shell-callable** (`rtk <cmd>`) — only tool using `updatedInput` transparent rewrite. Always runs after a Bash PASS decision, never blocks.

**context-mode is a plugin** — its own hooks run independently via `.claude-plugin/`. Do not duplicate its logic in our pipeline.

**Extension tiering for jCodeMunch** (route Tier 1 only in Phase 1):
- Tier 1: 45 extensions, full tree-sitter extraction → always route to jCodeMunch
- Tier 2: ~5 extensions, text-only → Phase 1: PASS, log hit for 1.4 validation
- Tier 3: ~8 extensions, regex-based → Phase 1: PASS, log hit for 1.4 validation

**jDocMunch** supports 20 extensions across 10 parsers. `.json`/`.yaml` only if OpenAPI structure.

**Thresholds:**
- Bash output: >20 lines → context-mode `ctx_execute`
- Data files: >100 lines → context-mode `ctx_execute_file`

**Hook execution order (PreToolUse):**
`jmunch-session-gate` → `scripts/engine.py` (single catch-all hook, handles all tool routing internally via `config/mappings.json`) → `continuous-learning observe.sh`

**Logging:** `scripts/observe/logger.py` → `~/.claude/logs/actions.jsonl` (configurable via `CC_ACTION_LOG`). Pure Python, no `lib/log.sh` dependency. One JSONL entry per PreToolUse event.
