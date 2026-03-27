# dd-cc-setup — TODO Tracker

> **This file is the source of truth.** Every step we take is tracked here.
> Plans are linked from steps. Steps are linked from plans. Nothing happens off-book.

---

## Phase 0: Decision Framework & Data Structures

> **No code.** Define how we categorize actions, make routing decisions, and structure our data.

### Decision Registry — Phase 0
| # | Decision | Outcome | Decided | Linked Step |
|---|----------|---------|---------|-------------|
| D0.1 | Pipeline model | Per-tool → per-matcher → ordered step list. Steps chain context. | 2026-03-26 | 0.1, 0.2 |
| D0.2 | Matcher = classification | Merged. Category is a property of the matcher, not a separate step. | 2026-03-26 | 0.1 |
| D0.3 | Observation level | Per-matcher config, not per-step. Engine wraps automatically between steps. | 2026-03-26 | 0.1 |
| D0.4 | Check failure behavior | Configurable per check: `on_failure: "abort"` or `"continue"` | 2026-03-26 | 0.2 |
| D0.5 | Step types | 4 types: check, transform, decide, resolve. All same Python interface (context → context). | 2026-03-26 | 0.2 |
| D0.6 | Pattern choice | Hybrid: Pipeline + Strategy with config-driven rules and per-rule pipelines | 2026-03-26 | 0.1 |
| D0.7 | Fallback behavior | Log + pass through. Unmatched calls always observed, then pass. | 2026-03-26 | 0.2 |
| D0.8 | Matcher ordering | First match wins. Matchers evaluated in config order. | 2026-03-26 | 0.2 |
| D0.9 | Algorithm shape | Decision Tree (If-Then Rules). Logic in Python methods, not config. | 2026-03-27 | 0.5 |
| D0.10 | Intent detection | Transcript-based `previous_tool` + `is_retry`. Replaces /tmp sentinel files. | 2026-03-27 | 0.5 |
| D0.11 | Tool axes | Orthogonal: jCodeMunch/jDocMunch=data type, context-mode=volume, RTK=command pattern | 2026-03-27 | 0.5 |
| D0.12 | RTK integration | Post-decision transform on Bash PASS. Not a routing decision. | 2026-03-27 | 0.5 |
| D0.13 | Extension tiering | 3 tiers for jCodeMunch (full/text/regex), flat for jDocMunch. From source code. | 2026-03-27 | 0.5 |

### 0.1 — Define the categorization model
- **Status:** ✅ Done
- **Goal:** How do we categorize a Claude Code action? What are the dimensions?
- **Output:** Categorization merged into matcher (D0.2). Category is a property of each matcher.
- **Plan:** `~/.claude/plans/atomic-wobbling-crystal.md`

### 0.2 — Define the decision/routing data structure
- **Status:** ✅ Done
- **Goal:** Design the JSON schema for the pipeline config
- **Output:** Per-tool → per-matcher → ordered steps. Full schema in plan.
- **Plan:** `~/.claude/plans/atomic-wobbling-crystal.md`
- **Decisions:** D0.1 through D0.8

### 0.3 — Map all Claude Code hook points
- **Status:** ✅ Done
- **Goal:** Enumerate every hook point Claude Code exposes and determine where we need to intercept
- **Output:** Hook point inventory doc
- **Plan:** `docs/plans/002-hook-point-inventory.md`
- **Key findings:**
  - 25 total hook events in Claude Code
  - We need 7: PreToolUse (routing+obs), PostToolUse (obs), PostToolUseFailure (obs), SessionStart (init), PreCompact (obs), PostCompact (re-init), Stop (summary)
  - **Full pipeline only runs on PreToolUse.** All other hooks are init, observation-only, or summary.
  - All our needed events support command hooks (shell → Python)
- **Tool repo extraction (4 tools):**
  - **jCodeMunch:** 3 hooks — PreToolUse Read Guard (Bash/Grep/Glob), PreToolUse Edit Guard (Edit/Write/MultiEdit), PostToolUse Index Hook (re-index after write)
  - **jDocMunch:** No hooks shipped — pure MCP today. Our system must implement same pattern as jCodeMunch: PreToolUse Doc Read Guard (Read/Bash/Grep on doc files), PostToolUse Doc Index Hook (re-index after writes).
  - **RTK:** 1 hook — PreToolUse Auto-Rewrite (Bash only, transparent rewrite via `updatedInput`)
  - **context-mode:** 2 hooks — PreToolUse (Bash/WebFetch/Read/Grep + MCP tools, security+routing), SessionStart (KB init)
  - **Critical overlap:** Bash has 3-way conflict (jCodeMunch/RTK/context-mode), Grep has 2-way (jCodeMunch/context-mode). Pipeline matcher ordering must resolve.
  - **Original 7-hook list validated.** PreToolUse/PostToolUse/SessionStart confirmed by tools; remaining 4 are our observability additions.

### 0.4 — Design the extensibility model
- **Status:** ✅ Done (covered by architecture)
- **Goal:** How do we add a new tool/route without rewriting the system?
- **Output:** New tool = add matcher block in JSON + optional Python function. No engine changes needed. (D0.1, D0.6)
- **Plan:** `~/.claude/plans/atomic-wobbling-crystal.md`

### 0.5 — Define decision factors & categorization algorithm
- **Status:** ✅ Done
- **Blocked by:** 0.1, 0.2
- **Goal:** For each tool/flow, define what the actual decision factors are (file type, size, command pattern, intent, session state, thresholds). What logic goes inside each matcher and each step?
- **Output:** Decision factors taxonomy (5 factors), per-tool decision trees, extension lists from source code, tool selection rules
- **Plan:** `docs/plans/006-decision-factors.md`
- **Decisions:** D0.9 through D0.13
- **Key findings:**
  - 5 decision factors in priority order: Intent → Data Type → Volume → Index Availability → Session State
  - Tools operate on **orthogonal axes**: jCodeMunch/jDocMunch=data type, context-mode=volume, RTK=command pattern
  - jCodeMunch has 3 support tiers (45 full extraction, 5 text-only, 8 regex-based) — not all code extensions equal
  - jDocMunch supports 20 extensions across 10 parsers; `.json`/`.yaml` are conditional (OpenAPI only)
  - RTK operates on 32 command patterns, not file extensions; always runs as post-decision transform
  - context-mode is extension-agnostic; thresholds: >20 lines, >5KB intent search, >100KB truncation
  - Intent is the highest-priority factor: modification intent (previous_tool=Edit/Write) always PASS
  - `is_retry` replaces /tmp sentinel files as loop-breaker (transcript-based, not filesystem)
  - Grep should redirect to `search_text` (not `search_symbols`) for code files

### 0.6 — Explore CLI tooling provided by the 4 tools
- **Status:** ✅ Done
- **Blocked by:** 0.3
- **Goal:** Inventory all CLI commands, entry points, and invocation patterns each tool provides. Our hooks will call these — we need to know exactly what's available.
- **Output:** CLI tooling inventory doc
- **Plan:** `docs/plans/003-cli-tooling-inventory.md`
- **Key findings:**
  - **RTK:** Fully shell-callable (`rtk <cmd>`), 31 commands, sub-10ms startup. Only tool that uses `updatedInput` rewrite pattern.
  - **jCodeMunch:** Partial shell CLI — `watch`, `hook-event` callable. Indexing is MCP-only.
  - **jDocMunch:** MCP-only. No shell CLI for index/search operations.
  - **context-mode:** MCP-only + plugin hooks. No direct CLI.
  - **Key insight:** Our pipeline primarily uses deny + redirect message (exit 2 + suggest MCP tool). Only RTK uses transparent rewrite via `updatedInput`.

### 0.7 — Explore agent hook behavior & context feeding
- **Status:** ✅ Done
- **Blocked by:** 0.3
- **Goal:** Understand how hooks interact with subagent spawning. Do agents fire hooks? How can we feed agents the right context so they know how to behave (tool routing, MCP instructions)?
- **Output:** Agent hook behavior doc
- **Plan:** `docs/plans/004-agent-hook-behavior.md`
- **Key findings:**
  - **Agent tool fires PreToolUse — YES.** `agent-gate-strict.sh` proves it. Receives `tool_input.prompt` and `tool_input.subagent_type`.
  - **Spawned agents' tool calls do NOT fire parent hooks.** Tool policies must be injected INTO the agent prompt.
  - **additionalContext does NOT propagate to subagents.** Only the parent LLM sees it.
  - **Current pattern:** deny-and-suggest (block, provide instructions, agent retries with instructions in prompt).
  - **Potential improvement:** Use `updatedInput.prompt` to inject routing context automatically. Unconfirmed if Claude Code supports this for Agent tool.
  - **SubagentStart/SubagentStop** not currently used but could enable agent lifecycle observability.

### 0.8 — Audit current hook ecosystem (beyond the 4 tools)
- **Status:** ✅ Done
- **Blocked by:** 0.3
- **Goal:** Inventory ALL hooks currently installed — not just the 4 core tools, but everything else calling or being called. What other tools, skills, and plugins register hooks that our system must coexist with?
- **Output:** Current hook ecosystem audit doc
- **Plan:** `docs/plans/005-hook-ecosystem-audit.md`
- **Key findings:**
  - **38 total hooks** across 8 event types: 16 custom shell scripts, 3 plugins with hooks (context-mode, security-guidance, superpowers), 1 skill (continuous-learning-v2), 2 external (fitness-track, notifications)
  - **Execution order documented:** jmunch-session-gate runs first on PreToolUse, then continuous-learning observe, then tool-specific hooks
  - **Unification candidates:** 8 custom hooks (unified-read-router, unified-bash-router, agent-gate-strict, webfetch-block, websearch-block, grep-observe, mcp-observe, track-genuine-savings) do what our pipeline is designed to do
  - **Must stay independent:** jmunch coordination system (sentinel), plugin hooks, continuous-learning, external integrations
  - **New events discovered in use:** WorktreeCreate, UserPromptSubmit, PreCompact (confirms our initial list)

### 0.9 — Explore Continuous Learning skill hook integration
- **Status:** ✅ Done
- **Blocked by:** 0.8
- **Goal:** Understand how the Continuous Learning v2.1 skill uses PreToolUse/PostToolUse hooks to capture session patterns as "instincts". Determine how this integrates with (or conflicts with) our observation and routing system.
- **Output:** Integration analysis doc
- **Plan:** `docs/plans/007-continuous-learning-integration.md`
- **Key findings:**
  - **Always exits 0 — never blocks.** Runs before jmunch-session-gate and routing hooks on PreToolUse.
  - **Storage:** `~/.claude/homunculus/projects/7fec5016c6e7/observations.jsonl` (JSONL, auto-rotates at 10MB)
  - **Fields captured:** timestamp, event type, tool name, input/output (max 5000 chars each), session ID, project context. Scrubs secrets automatically.
  - **PostToolUse blind spot:** Matcher is `Bash|Read|Edit|Write|Agent|Grep` only — MCP tool calls (jCodeMunch, jDocMunch, context-mode) are invisible to the learning system
  - **Observation timing gap:** PreToolUse fires before routing hooks, so blocked calls appear as "attempted" — creates false learning signals
  - **Project ID:** `7fec5016c6e7` (git remote URL hash) — clean slate, no instincts collected
  - **Recommendation: COMPLEMENT, don't replace.** Leave continuous-learning independent (generic user-behavior learning). Create parallel `routing-decisions.jsonl` written by our routing hooks.
  - Future opportunity: feed routing decisions as instincts (e.g., "prefer-jcodemunch-for-code-files")

### 0.10 — Explore observe.sh hooks & observation infrastructure
- **Status:** ✅ Done
- **Blocked by:** 0.8
- **Goal:** Understand the existing `observe.sh` hook pattern and how observation hooks are enabled in `settings.local.json`. This is the foundation our Phase 1 observability will build on.
- **Output:** Observation infrastructure doc
- **Plan:** `docs/plans/008-observation-infrastructure.md`
- **Key findings:**
  - **4 passive observation hooks:** `grep-observe.sh`, `mcp-observe.sh`, `track-genuine-savings.sh`, `observe.sh` — all always exit 0
  - **Shared infrastructure:** `lib/log.sh` provides `log_hook_event()` → `~/.claude/hooks/hook-events.jsonl` (~18K entries, JSONL)
  - **Current schema:** `{ts, hook, event, decision, detail, latency_ms}`
  - **Execution order (PreToolUse):** jmunch-session-gate → observe.sh → unified-read-router → ... → grep-observe → mcp-observe
  - **Critical:** `observe.sh` fires BEFORE routing hooks — blocked calls appear as "attempted" in learning log (false signals)
  - **track-genuine-savings.sh:** Already tracking 7.5M tokens saved via jCodeMunch/jDocMunch MCP tools
  - **Phase 1 verdict:** Build directly on `lib/log.sh` — import it in routing hooks, log decisions to same `hook-events.jsonl`
  - **Schema gaps to fill:** `tool_use_id`, `intent`, `previous_tool`, `is_retry`, `category`, `decision_factors`, `redirect_to`, `session_id`

### 0.11 — Phase 0 synthesis: extract rules, learnings & decisions into future-phase context
- **Status:** ✅ Done
- **Blocked by:** 0.5, 0.9, 0.10
- **Goal:** Walk through every completed Phase 0 step, plan doc, and decision registry entry. Extract all rules, learnings, constraints, and open questions discovered during exploration. Transform them into concrete, actionable context attached to the tasks in Phase 1, 2, and 3.
- **Output:** Synthesis doc categorizing all Phase 0 findings into pre-Phase-1 foundations, Phase 1 context, Phase 2 context, and current state baseline.
- **Plan:** `docs/plans/009-phase0-synthesis.md`
- **Key findings:**
  - **Pre-Phase-1 (implement first):** Rewrite `config/mappings.json` to new schema + create `scripts/` directory scaffolding → new tasks 0.12 + 0.13
  - **Extension ownership is mostly unambiguous:** 45 Tier-1 code extensions go to jCodeMunch, 20 doc extensions go to jDocMunch, tiny overlap zone (~5 extensions need extra logic)
  - **Routing hooks replace 8 existing hooks:** unified-read-router, unified-bash-router, agent-gate-strict, webfetch-block, websearch-block, grep-observe, mcp-observe, track-genuine-savings → new migration task 2.10
  - **observe.sh ordering creates false learning signals** (fires before routing blocks) — open decision OD.1 before Phase 1 starts
  - **lib/log.sh is the right foundation** for Phase 1 observation hooks — extend schema, don't replace
  - **4 open decisions** before Phase 1 coding can start (see 009-phase0-synthesis.md section "Open Decisions")

### 0.12 — Rewrite `config/mappings.json` to new schema
- **Status:** ✅ Done
- **Blocked by:** 0.11
- **Goal:** Replace the current old-schema mappings.json with the architecture-plan schema: tool → matcher (description + ordered method list). This is the config the engine reads — must exist before Phase 1 coding starts.
- **Plan:** `docs/plans/009-phase0-synthesis.md` (section G1.1)
- **Output:** `config/mappings.json` — version 2.0, tool → matchers[] → steps[]. Active routing: Read (3 matchers), Bash (1), WebSearch (1), WebFetch (1). Pass-through list for all other tools + MCP prefixes.

### 0.13 — Create `scripts/` directory scaffolding
- **Status:** ✅ Done
- **Blocked by:** 0.12
- **Goal:** Create the empty `scripts/engine.py`, `scripts/matchers/base.py`, `scripts/steps/base.py` with docstrings only. No logic — just the structure Phase 1 will fill in.
- **Plan:** `docs/plans/009-phase0-synthesis.md` (section G1.2)
- **Output:** `scripts/engine.py`, `scripts/matchers/__init__.py`, `scripts/matchers/base.py`, `scripts/steps/__init__.py`, `scripts/steps/base.py` — docstrings only.

---

## Phase 1: Observability

> Build the observation layer — hook scripts that capture every action, categorize it, and log the outcome.

### Decision Registry — Phase 1
| # | Decision | Outcome | Decided | Linked Step |
|---|----------|---------|---------|-------------|
| D1.1 | OD.1 — Hook ordering: continuous-learning observe.sh fires before routing hooks | Accept noise in Phase 1. Phase 2 task 2.11: reorder so routing fires first in new system. | 2026-03-27 | 2.11 |
| D1.2 | OD.2 — Unified log vs separate routing-decisions.jsonl | **Revised (2026-03-27):** New file `~/.claude/logs/actions.jsonl` (configurable via `CC_ACTION_LOG`). Python engine writes JSONL directly — no lib/log.sh dependency. See spec `docs/superpowers/specs/2026-03-27-observability-pipeline-design.md`. | 2026-03-27 | 1.1 |
| D1.3 | OD.3 — Tier 2/3 jCodeMunch extensions worth routing? | Tier 1 only in Phase 1. Log Tier 2/3 hits with `tier: 2/3` tag. Promote in Phase 2 if 1.4 validates. | 2026-03-27 | 1.2, 2.2 |
| D1.4 | OD.4 — `tool_use_id` available in hook stdin? | **Resolved (task 1.5):** Present. Use `tool_use_id` as pre→post correlation key. Full fields confirmed: `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`. | 2026-03-27 | 1.5 |

### 1.1 — Build the observation hook script(s)
- **Status:** ✅ Done (2026-03-27)
- **Blocked by:** 0.12, 0.13
- **Goal:** Hook scripts that intercept tool calls and log them as JSON
- **Plan:** `docs/superpowers/specs/2026-03-27-observability-pipeline-design.md`
- **What was built:**
  - ~~Import `lib/log.sh`~~ → Pure Python logger (`scripts/observe/logger.py`)
  - ~~Log to `~/.claude/hooks/hook-events.jsonl`~~ → New file `~/.claude/logs/actions.jsonl` (D1.2 revised)
  - Schema fields implemented: `tool_name`, `tool_use_id`, `session_id`, `category`, `decision`, `redirect_to`, `decision_factors` (nested dict), `errors`, `steps_trace`, `latency_ms`
  - 7 hook events originally planned — **Phase 1: PreToolUse only** (others deferred to task 2.14)
  - Execution order: `jmunch-session-gate` → `scripts/engine.py` (single catch-all hook)
  - **D1.1 resolved:** Accept noise in Phase 1 — continuous-learning `observe.sh` fires before routing hooks and will log blocked calls as "attempted". Phase 2 task 2.11 fixes ordering.
  - **D1.2 resolved:** New file `~/.claude/logs/actions.jsonl`. Python engine writes directly — no `lib/log.sh`.
  - **D1.4 resolved:** `tool_use_id` IS present. Used as correlation key in `HookInput` and every log entry.

### 1.2 — Implement the categorization engine
- **Status:** ✅ Done (2026-03-27)
- **Blocked by:** 0.12, 0.13
- **Goal:** Python pipeline walker that reads config/mappings.json and chains steps per matcher
- **Plan:** `docs/superpowers/specs/2026-03-27-observability-pipeline-design.md`
- **Key context from Phase 0:**
  - All steps share the same Python interface: `step(context: dict) → dict` (D0.5)
  - 4 step types: check, transform, decide, resolve — same interface, different semantics
  - First-match-wins on matchers (D0.8); `on_failure: "abort"` halts pipeline (D0.4)
  - Decision factors in priority order: Intent → Data Type → Volume → Index → Session (D0.9)
  - Intent detection is transcript-based: `previous_tool` from tail of transcript (~1ms); `is_retry` = same tool + same input as previous call (D0.10)
  - Degradation policy: when jq or a tool is unavailable, warn and PASS — never silently deny
  - `is_retry` replaces all `/tmp` sentinel files — transcript-based loop-breaking (D0.10)

### 1.3 — Token savings measurement
- **Status:** 🔴 Not started
- **Blocked by:** ~~1.1, 1.2~~ (both done — unblocked)
- **Goal:** Calculate and report how much was saved, what's still leaking
- **Plan:** _TBD_
- **Key context from Phase 0:**
  - `track-genuine-savings.sh` already measures jCodeMunch/jDocMunch sliced-read savings (7.5M tokens). Do NOT duplicate.
  - Phase 1 adds: routing-decision savings (tokens saved by redirecting a Read that would have loaded N lines)
  - Net formula: (raw Read cost) − (redirect overhead) − (MCP response cost)
  - Use transcript mining baselines from 1.4 for per-extension token cost estimates
  - Per-tool breakdown: how much each redirect type saves on average

### 1.5 — Empirically test `tool_use_id` availability in hook stdin
- **Status:** ✅ Done
- **Blocked by:** —
- **Goal:** Confirm whether Claude Code includes `tool_use_id` in the PreToolUse hook stdin JSON. Result feeds D1.4 — determines our pre→post correlation key strategy.
- **Plan:** `hooks/test-stdin-dump.sh` (kept as reference, not registered)
- **Method:** Write a 3-line test hook that dumps raw stdin to `/tmp/hook-stdin-test.json`, register it on PreToolUse:Read, trigger one Read call, inspect the output.
- **Result (D1.4 resolved):** `tool_use_id` IS present. Full payload fields: `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`. Use `tool_use_id` as the pre→post correlation key.
- **Additional discovery (from changelog, not yet empirically tested):**
  - Claude Code changelog confirms: `agent_id` (for subagents) and `agent_type` (for subagents and `--agent`) are included in hook event stdin JSON.
  - `CLAUDE_AGENT_NAME` env var is also set for subagent processes (confirmed in use by `track-genuine-savings.sh`).
  - Task 1.5 tested from **main session only** — `agent_id`/`agent_type` would be absent there. Need subagent-context test (see 1.5b below).
  - **Routing implication:** `agent_type` is a strong intent signal. Explore/Plan agents can't Edit/Write (excluded from their toolset), so `agent_type in (Explore, Plan)` = guaranteed research intent. This is more reliable than `previous_tool` for agent contexts.
  - **Agent-type matching tiers for decision-making:**
    - Read-only agents (Explore, Plan, security-auditor, cloud-architect, architect, observability-expert) → research intent, safe to redirect to jCodeMunch/jDocMunch
    - Code-writing agents (python-expert, typescript-expert, react-expert, nextjs-expert, docker-expert) → may need raw Read before Edit, treat as modification intent
    - Review agents (code-reviewer, python-reviewer, java-reviewer) → research intent but may need raw content for line-level review — log and validate in Phase 1
    - No agent_id (main session) → fall through to `previous_tool` / other factors
  - This is a new decision axis: **WHO** is calling (orthogonal to data-type and volume axes from D0.11).

### 1.5b — Empirically test `agent_id`/`agent_type` availability in subagent hook stdin
- **Status:** 🔴 Not started
- **Blocked by:** —
- **Goal:** Confirm `agent_id` and `agent_type` fields appear in hook stdin when hooks fire inside a subagent context. Also check `CLAUDE_AGENT_NAME` env var.
- **Method:** Register a test hook on PreToolUse:Read that dumps stdin + env to `/tmp/hook-stdin-agent-test.json`. Spawn an Explore agent that triggers a Read. Inspect the dump.
- **What to capture:**
  - Presence/absence of `agent_id` and `agent_type` in stdin JSON
  - Value of `CLAUDE_AGENT_NAME` env var
  - Whether `session_id` is the same as the parent session or different
  - Whether `transcript_path` points to a separate transcript or the parent's
  - Whether `permission_mode` reflects the agent's mode or inherits from parent
- **Feeds:** HookInput dataclass update (add `agent_id`, `agent_type` optional fields), decision tree validation for agent-aware routing

### 1.6 — Implement transcript-based decision factors (previous_tool, is_retry)
- **Status:** 🔴 Not started
- **Blocked by:** ~~1.1, 1.2~~ (both done — unblocked)
- **Goal:** Tail the session transcript to extract `previous_tool` and `is_retry` values that drive the Intent decision factor (highest priority in the 5-factor order).
- **Plan:** _TBD_
- **Notes:**
  - Both are stubbed as `None` in Phase 1 (observation-only). Implement in Phase 2 before enforcement.
  - `previous_tool`: read last tool call from transcript tail (~1ms). `Edit`/`Write` → PASS (modification mode).
  - `is_retry`: same `tool_name` + same `tool_input` as the previous call → PASS (loop-breaker, replaces /tmp sentinels).
  - Transcript path available in `HookInput.transcript_path` (confirmed in task 1.5).
  - See spec: `docs/superpowers/specs/2026-03-27-observability-pipeline-design.md`
  - Deferred from Phase 1 scope per design spec "Not In Scope" table.

### 1.4 — Mine historical transcript logs for baseline statistics
- **Status:** 🔴 Not started
- **Blocked by:** —
- **Goal:** Analyze `~/.claude/projects/*/` transcript JSONL files to extract baseline token usage, tool call patterns, Read→Edit sequences, and per-action token costs. This data feeds routing threshold calibration and validates decision factor predictions.
- **Plan:** _TBD_
- **Notes:**
  - Transcripts contain full tool_use blocks with tool_name, tool_input, and usage (token counts)
  - Key analyses: Read→Edit pair frequency, tool call sequences, per-extension token costs, permission_mode distribution, agent_type patterns
  - Step 0.5 research already proved: `previous_tool` is the strongest intent predictor (89% accuracy), `offset/limit` is useless (22%)
  - Should produce: baseline token cost per tool, waste percentage (analysis reads that could have been redirected), editing-mode vs exploration-mode session ratios
  - Can run independently of other Phase 1 work — no dependencies
- **Extended draft decision trees to calibrate** (from 0.5 + hook bug analysis — NOT final, many unvalidated assumptions):
  - These trees include edge cases discovered from analyzing current hooks (`unified-read-router.sh`, `unified-bash-router.sh`, `jmunch-session-gate.sh`, `agent-gate-strict.sh`, etc.)
  - This step must validate each rule with real data and remove/adjust rules that don't hold up
  - **Read tree (extended):**
    1. `/dev/*` or `/proc/*` → PASS (system paths)
    2. symlink outside `$HOME` → HARD_DENY (security)
    3. global exception file → PASS (CLAUDE.md, README.md, conftest.py, planning files)
    4. `agent_id` present → PASS (subagents never edit)
    5. `is_retry` (same file as previous denied Read) → PASS (loop-breaker)
    6. `permission_mode` = "plan" → DENY + redirect
    7. `file_size` < threshold → PASS (small file, cheap read)
    8. index not fresh → SOFT_DENY (force refresh)
    9. `previous_tool` = Edit/Write → PASS (editing mode)
    10. `extension` = code → DENY + redirect jCodeMunch
    11. `extension` = doc → DENY + redirect jDocMunch
    12. fallback → PASS
  - **Bash tree (extended):**
    1. missing jq/dependencies → PASS (fail-open)
    2. contains `$()` or backticks → PASS + RTK (unparseable)
    3. contains `&&` or `||` → PASS + RTK (chained, RTK handles)
    4. output redirection (`>` or `>>`) → PASS + RTK
    5. `agent_id` present → PASS
    6. `is_retry` → PASS
    7. security violation pattern → HARD_DENY
    8. cat/head/tail on code file → DENY + jCodeMunch
    9. cat/head/tail on doc file → DENY + jDocMunch
    10. unbounded git log/diff → DENY + redirect context-mode
    11. git write ops (add, commit, push) → PASS + RTK
    12. safe utilities (mkdir, touch, etc.) → PASS + RTK
    13. unbounded output pattern → DENY + redirect context-mode
    14. fallback → PASS + RTK
  - **Grep tree:** `agent_id` → `is_retry` → code target → doc target → large output → fallback PASS
  - **Glob tree:** `agent_id` → `is_retry` → code exploration pattern → fallback PASS
  - **WebSearch:** always HARD_DENY → Exa
  - **WebFetch:** always HARD_DENY → context-mode ctx_fetch_and_index
  - **Agent:** prompt missing jCodeMunch/jDocMunch instructions → SOFT_DENY + inject; else PASS
  - **Edit/Write:** always PASS + PostToolUse re-index
- **Key learnings from current hook bug analysis** (feed into calibration):
  - `/tmp` sentinel files unreliable (cross-session collisions, reboot clears) — replaced by transcript-based `is_retry`
  - Small files pass through size threshold — no need for hardcoded exception file lists (CLAUDE.md etc.)
  - Bash chained commands (`&&`, `||`) and subshells (`$()`, backticks) are unparseable — always delegate to RTK
  - RTK version checking is fragile — engine should validate tool availability at startup, not per-call
  - Silent index fallback (missing jCodeMunch/jDocMunch) masks misconfiguration — engine should warn, not silently degrade
  - Bounded vs unbounded git output is RTK's concern, not a routing decision
  - All current hooks fail-open on missing jq — engine must define explicit degradation policy

---

## Phase 2: Hook Routing System

> The intelligent routing layer — categorize actions and steer them to token-efficient tools.

### Decision Registry — Phase 2
| # | Decision | Outcome | Decided | Linked Step |
|---|----------|---------|---------|-------------|
| D2.1 | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 2.1 — Implement routing decision engine
- **Status:** 🔴 Not started
- **Blocked by:** Phase 0, Phase 1 (need observation baseline)
- **Goal:** Engine that reads the JSON mappings and makes pass/deny/redirect decisions
- **Plan:** _TBD_
- **Key context from Phase 0:**
  - Decision tree algorithm (D0.9): if-then rules, first match wins, logic in Python methods
  - Priority: Intent (1st) → Data Type (2nd) → Volume (3rd) → Index (4th) → Session (5th) (D0.9)
  - Intent FIRST: `previous_tool = Edit/Write` → always PASS (modification mode, Claude needs raw content)
  - `is_retry` (same tool+input as prior call) → always PASS (loop-breaker)
  - Extension lookup is fast and unambiguous for ~90% of cases (see 009-phase0-synthesis.md section 3.A)
  - RTK is a post-decision transform, not a routing decision — always runs on Bash PASS (D0.12)
  - Conflict resolution order for Bash: jCodeMunch cat > context-mode unbounded > RTK fallback

### 2.2 — Build hook scripts for the 4 core tools
- **Status:** 🔴 Not started
- **Blocked by:** 2.1
- **Goal:** Hook scripts that route to jDocMunch, jCodeMunch, RTK, context-mode
- **Plan:** _TBD_
- **Key context from Phase 0:**
  - jCodeMunch and jDocMunch are **MCP-only** — hooks cannot call them directly (0.6). Exit 1 + message: `"BLOCKED: Use mcp__jcodemunch__get_symbol_source instead"`
  - RTK has full shell CLI (`rtk <cmd>`) — use via `updatedInput` transparent rewrite (0.6)
  - context-mode is a **plugin** — its own hooks run independently; don't duplicate (0.8, 2.8)
  - Extension lists: 45 Tier-1 + 5 Tier-2 + 8 Tier-3 for jCodeMunch; 20 for jDocMunch (0.5)
  - **D1.3 resolved:** Tier 1 extensions only in Phase 1. Log Tier 2/3 hits with `tier` tag for 1.4 to measure. Promote to routing in Phase 2 if transcript data justifies.
  - Agent routing: inject instructions into agent prompt on deny; investigate `updatedInput.prompt` (0.7)

### 2.3 — Validate routing with observability data
- **Status:** 🔴 Not started
- **Blocked by:** 2.2, 1.3
- **Goal:** Confirm routing decisions match expectations, measure token reduction
- **Plan:** _TBD_

### 2.4 — jCodeMunch watch mode lifecycle management
- **Status:** 🔴 Not started
- **Blocked by:** 0.6, 2.1
- **Goal:** Design and implement how jCodeMunch `watch` mode starts for the current project directory when Claude Code launches, and how to prevent duplicate watchers across sessions.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - `uvx jcodemunch-mcp watch --watcher-path .` needs to start at SessionStart or as part of an alias
  - Must detect if a watcher is already running for this directory (PID file? lock file? process check?)
  - Tie watcher lifecycle to the CLI session — watcher should stop when session ends (or idle-timeout)
  - `--watcher-idle-timeout` flag exists — explore if sufficient
  - Alternative: `watch-claude` subcommand auto-discovers worktrees — may solve this
  - Must not spawn duplicate watchers on session restart / compact / re-init

### 2.5 — jDocMunch PostToolUse re-indexing strategy
- **Status:** 🔴 Not started
- **Blocked by:** 0.6, 2.1
- **Goal:** Design how jDocMunch re-indexes doc files after writes, given it has no direct shell CLI for indexing (MCP-only).
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - jDocMunch has no shell-callable `index_file` — only MCP `index_local`
  - PostToolUse hook for `Edit`/`Write` on doc files needs to trigger re-index somehow
  - Options: (a) call the running MCP server instance, (b) use `additionalContext` to tell Claude to re-index, (c) rely on session-level periodic re-index, (d) pipe to `uvx jdocmunch-mcp serve --transport stdio` from shell
  - Same pattern as jCodeMunch's Index Hook, but without the shell CLI convenience
  - Must decide: immediate re-index vs deferred (next read triggers re-index)

### 2.6 — jCodeMunch PostToolUse conditional re-indexing
- **Status:** 🔴 Not started
- **Blocked by:** 0.6, 2.4
- **Goal:** Design PostToolUse re-indexing that only fires when files actually changed, and handles overlap with the watch mode gracefully.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - Re-index should only trigger on actual file changes (Edit/Write success), not on reads
  - If watcher is running, PostToolUse re-index is a safety net (double-index on subset = acceptable)
  - Watcher uses `--watcher-debounce` (default 2000ms) — PostToolUse hook fires immediately, watcher follows
  - PostToolUse hook calls `uvx jcodemunch-mcp index_file` via MCP (not shell) — same as current jCodeMunch Index Hook
  - Must detect: was the file actually modified? (check tool_output for success vs failure)
  - Incremental indexing (`incremental=true`) makes double-index cheap — only changed files re-processed

### 2.7 — RTK hook conflict detection & ownership
- **Status:** 🔴 Not started
- **Blocked by:** 0.8, 2.1
- **Goal:** Our system will drive RTK's Bash rewriting flow. Design a check that detects if RTK's own hooks (`rtk-rewrite.sh`) are also registered, and error/warn to prevent double-rewriting.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - RTK installs its own `rtk-rewrite.sh` in `~/.claude/hooks/` via `rtk init -g`
  - Our unified pipeline will handle RTK rewriting as a pipeline step (Bash matcher → RTK rewrite)
  - If BOTH our pipeline AND `rtk-rewrite.sh` are registered on PreToolUse:Bash, commands get rewritten twice
  - Need a startup check (SessionStart?) that detects this conflict and either: (a) errors with clear message, (b) auto-disables RTK's standalone hook, (c) defers to RTK's hook and skips our pipeline step
  - Current `unified-bash-router.sh` already integrates RTK rewriting — this is the pattern to formalize
  - Also check: does `rtk init -g` overwrite our hooks on upgrade?

### 2.8 — context-mode hook coexistence strategy
- **Status:** 🔴 Not started
- **Blocked by:** 0.8, 2.1
- **Goal:** Plan how our pipeline coexists with context-mode's plugin hooks (`pretooluse.mjs`, `sessionstart.mjs`), since we do not control those hooks and they intercept the same tools.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - context-mode is a **plugin** — its hooks are registered via `.claude-plugin/hooks.json`, not our settings.json
  - context-mode's `pretooluse.mjs` intercepts: Bash, WebFetch, Read, Grep, Task, execute, execute_file, batch_execute
  - **Execution order question:** Do plugin hooks run before or after settings.json hooks? Or in parallel?
  - **Overlap:** Our pipeline intercepts Bash, Read, Grep on PreToolUse — same tools as context-mode
  - **Scenarios to handle:**
    - Our pipeline denies a Read → does context-mode's hook still fire?
    - Context-mode denies a Bash → does our pipeline's hook still fire?
    - Both deny the same call — which deny message does Claude see?
  - **Options:** (a) coordinate via shared state (sentinel-like), (b) let both run and accept that first-deny wins, (c) disable context-mode's hooks and replicate its logic in our pipeline, (d) make our pipeline context-mode-aware (check if context-mode already handled it)
  - Must test empirically: hook execution order between plugin hooks and settings.json hooks

### 2.11 — Reorder hooks: routing before continuous-learning observe
- **Status:** 🔴 Not started
- **Blocked by:** 2.2
- **Goal:** In the new settings.json configuration, ensure our routing hooks fire BEFORE the continuous-learning `observe.sh` on PreToolUse. This means continuous-learning only sees post-routing outcomes (actual decisions), not pre-routing attempts — eliminating false learning signals.
- **Plan:** _TBD_
- **Notes:**
  - Currently: slot 0 (`*`) runs jmunch-session-gate + continuous-learning together, before all routing hooks
  - New order: jmunch-session-gate (slot 0) → routing hooks (slot 1+) → continuous-learning observe (last)
  - Requires splitting the current slot-0 `*` entry and repositioning observe.sh
  - Validate: after reorder, a denied Read should NOT appear as "attempted" in `observations.jsonl`
  - D1.1 context: in Phase 1 we accept the false signals; this task fixes it in Phase 2

### 2.10 — Migration plan: replace 8 unification candidate hooks
- **Status:** 🔴 Not started
- **Blocked by:** 2.2, 2.3
- **Goal:** Plan and execute the replacement of the 8 existing custom hooks with the new pipeline. Run old and new in parallel, validate parity on real sessions, then decommission old hooks.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - 8 hooks to replace: `unified-read-router.sh`, `unified-bash-router.sh`, `agent-gate-strict.sh`, `webfetch-block.sh`, `websearch-block.sh`, `grep-observe.sh`, `mcp-observe.sh`, `track-genuine-savings.sh`
  - Must NOT break during migration — old hooks must stay active until new pipeline is validated
  - Run both in shadow mode: new pipeline logs its decisions but doesn't block; compare against old hook outcomes
  - Parity definition: new pipeline must produce the same DENY/PASS/redirect decisions as old hooks for all cases in 1.4 transcript baseline
  - After parity: disable old hooks from settings.json, verify no regressions over 1 session
  - Preserve `track-genuine-savings.sh` data continuity — new savings tracking must not reset the 7.5M token counter

### 2.9 — context-mode vs jCodeMunch comparison for large code files
- **Status:** 🔴 Not started
- **Blocked by:** 2.2, 1.4
- **Goal:** Empirically test when context-mode sandboxing is better than jCodeMunch symbol retrieval for code files. Measure token costs for both approaches on real files of varying sizes and languages.
- **Plan:** _TBD → `docs/plans/`_
- **Notes:**
  - jCodeMunch gives symbol-level retrieval (3-50 lines per symbol, 95%+ savings in retrieval-heavy workflows)
  - context-mode sandboxes the entire file (keeps raw content out of context, returns summary)
  - Overlap case: large code file where user wants broad understanding, not specific symbol
  - Need real token cost comparisons across: file sizes (50, 200, 500, 1000+ lines), languages (Tier 1 vs 2 vs 3), use cases (symbol lookup vs full-file understanding)
  - May inform a new decision rule: "if file > X lines AND intent = broad understanding → context-mode over jCodeMunch"

### 2.12 — Debug logging levels (configurable verbosity)
- **Status:** 🔴 Not started
- **Blocked by:** ~~1.1, 1.2~~ (both done — unblocked)
- **Goal:** Expose `observe.level` (info/debug) via an environment variable so verbosity can be changed at runtime without editing mappings.json.
- **Plan:** _TBD_
- **Notes:**
  - `observe.level` per-matcher in mappings.json is the primary mechanism (Phase 1).
  - Add `CC_OBSERVE_LEVEL` env var override: `debug` forces `steps_trace` in all entries; `info` suppresses it globally.
  - `debug` level: full `steps_trace` in JSONL. `info` level: `steps_trace: []`.
  - Deferred from Phase 1 scope per design spec "Not In Scope" table.

### 2.13 — Logs retention / rotation / cleanup
- **Status:** 🔴 Not started
- **Blocked by:** ~~1.1~~ (done — unblocked)
- **Goal:** Define max size, rotation policy, and cleanup strategy for `~/.claude/logs/actions.jsonl`.
- **Plan:** _TBD_
- **Notes:**
  - `actions.jsonl` will grow unbounded without rotation — define policy before production use.
  - Options: max file size (e.g. 50MB) → rotate to `actions.jsonl.1`, max N rotations; or time-based (daily/weekly).
  - Should rotation happen in the engine on each write (check size before write) or via a separate cron/cleanup script?
  - Also: define what "cleanup" means — delete old rotations or archive them?
  - Deferred from Phase 1 scope per design spec "Not In Scope" table.

### 2.14 — Extend engine to PostToolUse / SessionStart / other hook events
- **Status:** 🔴 Not started
- **Blocked by:** 2.1
- **Goal:** Register `engine.py` on additional hook events beyond PreToolUse, starting with PostToolUse (for re-indexing) and SessionStart (for init).
- **Plan:** _TBD_
- **Notes:**
  - Phase 1 targets PreToolUse only. Engine architecture supports other events — needs registration + matcher config.
  - PostToolUse: trigger re-indexing on Edit/Write success (links to tasks 2.5, 2.6).
  - SessionStart: validate tool availability, warm indexes, detect RTK/context-mode conflicts (links to 2.4, 2.7).
  - Other candidates: PreCompact (flush/snapshot logs), PostCompact (re-init indexes).
  - Deferred from Phase 1 scope per design spec "Not In Scope" table.

### 2.15 — Indexing triggers design
- **Status:** 🔴 Not started
- **Blocked by:** 2.4, 2.5, 2.6, 2.14
- **Goal:** Design a unified policy for when jCodeMunch/jDocMunch indexes are triggered to re-index: PostToolUse, SessionStart, file watcher, or on-demand.
- **Plan:** _TBD_
- **Notes:**
  - Existing triggers: PostToolUse after Edit/Write (tasks 2.5, 2.6), watch mode (task 2.4).
  - Questions: Should SessionStart always re-index? What if index is fresh (indexed < 5min ago)?
  - File watcher (jCodeMunch watch mode) vs PostToolUse hook: are they complementary or redundant?
  - Deferred from Phase 1 scope per design spec "Not In Scope" table.

---

## Phase 3: Deployment & Portability _(future — notes only)_

> Not actively planned yet. Capture notes here as they come up during earlier phases.

- **Intent:** Package the system so it works across multiple projects
- **Open questions:** Portable configs? Install script? Package? TBD when we get here.
- **Notes:**
  - _(add notes here as Phase 0–2 work surfaces deployment considerations)_
  - **v1.0 Python code removal:** On global deploy, remove `scripts/capture/`, `scripts/categorise/`, `scripts/routing/` — these are dead code kept only as reference during Phase 1/2 development. Remove only after Phase 2 pipeline is validated in production.

---

---

## Backlog / Config Fixes

### B.1 — Fix broken status bar (window time display)
- **Status:** 🔴 Not started
- **Goal:** The Claude Code status bar is showing incorrect/broken window time. Diagnose and fix.
- **Notes:** _Add details here once root cause is known (statusline config? hook? terminal multiplexer?)_

---

_Last updated: 2026-03-27 — added tasks 1.6, 2.12–2.15; revised D1.2; Phase 3 v1.0 cleanup note_
