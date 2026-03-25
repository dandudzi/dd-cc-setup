# Claude Hooks Optimizer

## Project Purpose

This repo develops and tests an optimized hook system for Claude Code (`~/.claude/`). Hooks are developed and tested here in `hooks/`, then deployed to `~/.claude/hooks/` when the user explicitly says "deploy."

## Current Status: Deployed

All 7 new hooks + 2 hardened hooks deployed to `~/.claude/hooks/`. 9 retired hooks deleted. Settings.json updated. **367 assertions, 0 failures** across 10 test suites. Backup at `~/.claude/settings.json.bak`.

## Hooks

### New Hooks (7)

| Hook | Event | Behavior | Output |
|------|-------|----------|--------|
| `unified-read-router.sh` | PreToolUse:Read | Routes by extension: code→jCodeMunch, doc→jDocMunch, large JSON→context-mode, else→allow. Deny-first-allow-retry: first Read denied, second allowed (for Edit workflow). | JSON deny + exit 0 |
| `unified-bash-router.sh` | PreToolUse:Bash | Allow-list → RTK rewrite → unknown passthrough. Never blocks. `&&`/`||` flow through to RTK; only backtick/`$()` guarded. | JSON updatedInput or silent allow |
| `agent-gate-strict.sh` | PreToolUse:Agent | 3-tier classification: exempt/doc-only/code. Blocks agents missing tool instructions. | JSON deny + exit 0 |
| `webfetch-block.sh` | PreToolUse:WebFetch | Blocks all WebFetch, suggests ctx_fetch_and_index | Plain text + exit 2 |
| `websearch-block.sh` | PreToolUse:WebSearch | Blocks all WebSearch, suggests Exa/Context7/ctx | Plain text + exit 2 |
| `grep-observe.sh` | PreToolUse:Grep | Observability-only logger, never blocks | Silent exit 0 |
| `plugin-drift-check.sh` | SessionStart | Verifies context-mode plugin still covers expected matchers | Warning or silent exit 0 |

### Hardened Existing Hooks (2)

| Hook | Changes |
|------|---------|
| `jmunch-session-gate.sh` | python3→jq for JSON parsing, hook_guard trap, safe arithmetic defaults, JSON deny instead of exit 2, all MCP tools allowed through |
| `track-genuine-savings.sh` | hook_guard wrapper, python3 availability check |

### Shared Library

| File | Purpose |
|------|---------|
| `hooks/lib/log.sh` | `hook_guard` trap (never crash), `hook_timer_start` (ms timer), `log_hook_event` (structured JSONL) |

## Design Principles

- **Structural routing only** — route by known properties (file extension, RTK registry, command syntax). Never guess output size.
- **If we don't know → observe and pass through** — log unknown commands, don't block.
- **Never crash** — all hooks use `hook_guard`. Exit 0 (allow) or exit 2 (block), never exit 1.
- **Fail-open** — missing jq, malformed JSON, missing MCP index → exit 0.
- **Unified observability** — all hooks log to `~/.claude/hooks/hook-events.jsonl` with self-timing.
- **JSON deny for routers** — read-router and agent-gate use `hookSpecificOutput` with `permissionDecision: "deny"` + exit 0. Simple blockers use plain text + exit 2.
- **Deny-first-allow-retry for Read** — first Read of code/doc/data file is denied (suggests MCP). Second Read of same file is allowed (needed for Edit workflow). Marker cleaned on allow, so third Read is denied again.

## Directory Structure

```
hooks/                           # Hook implementations (deploy target: ~/.claude/hooks/)
  lib/log.sh                     # Shared logging + error resilience
  unified-read-router.sh         # Routes Read by file extension
  unified-bash-router.sh         # Allow-list → RTK rewrite → passthrough
  agent-gate-strict.sh           # 3-tier agent gate
  webfetch-block.sh              # Block WebFetch
  websearch-block.sh             # Block WebSearch
  grep-observe.sh                # Grep usage logger
  plugin-drift-check.sh          # SessionStart plugin coverage check
  jmunch-session-gate.sh         # Hardened: python3→jq + hook_guard
  track-genuine-savings.sh       # Hardened: hook_guard wrapper
tests/
  hooks/
    run-tests.sh                 # Main runner — all unit tests
    helpers/
      assertions.sh              # assert_exit, assert_json_field, assert_log_entry, etc.
      setup.sh                   # setup_test_env / teardown_test_env
      mock-input.sh              # mock_read_input, mock_bash_input, mock_agent_input, etc.
    unit/
      test-log-lib.sh            # 24 tests — lib/log.sh
      test-unified-read-router.sh # 114 tests — read routing + deny-first-allow-retry
      test-unified-bash-router.sh # 70 tests — bash routing + RTK + subshell guard
      test-agent-gate-strict.sh  # 44 tests — agent classification
      test-webfetch-block.sh     # 17 tests — WebFetch blocking
      test-websearch-block.sh    # 13 tests — WebSearch blocking
      test-grep-observe.sh       # 12 tests — Grep observability
      test-plugin-drift-check.sh # 14 tests — drift detection
      test-error-resilience.sh   # 41 tests — cross-cutting failure scenarios
      test-hardened-hooks.sh     # 27 tests — hardened hook resilience + MCP allow-through + JSON deny
prompts/                         # Session prompts for reproducibility
.claude/                         # Project-scoped Claude Code settings
```

## Running Tests

```bash
bash tests/hooks/run-tests.sh
```

## Observability

All hooks log to `~/.claude/hooks/hook-events.jsonl` with self-timing. See `docs/observability-queries.md` for jq query recipes.

## Known Constraints (learned from production)

1. **Claude Code cannot block MCP tools via exit 2.** Hooks returning exit 2 for `mcp__*` tool calls produce `hook error: No stderr output` instead of showing the block message. Any hook on the `*` matcher MUST allow MCP tools through (`case "$TOOL" in mcp__*) exit 0 ;; esac`). Fixed in jmunch-session-gate.sh.
2. **PreToolUse input for MCP tools has no `cwd` field.** Hooks that derive project identity from `cwd` must fall back to `git rev-parse --show-toplevel`. If the hook subprocess runs outside a git repo, the fallback `pwd` may resolve to the wrong project.
3. **SessionStart index triggers are best-effort.** `jmunch-session-start.sh` outputs instructions for the model to run indexes, but competing SessionStart hooks and the user's first message can preempt it. The sentinel may not exist when PreToolUse hooks fire. The gate's auto-bypass (MAX_BLOCKS=4) is the safety net.
4. **Hook errors persist within a session.** Fixing a hook file doesn't affect the current running session — Claude Code may cache hook behavior. Fixes take effect on new sessions.
5. **`hook_guard` trap does not catch errors before it's installed.** If `source lib/log.sh` fails silently (2>/dev/null), `hook_guard` is undefined and calling it exits 127 with no trap to catch it. The source path must be reliable.

## Backlog

See `TODO.md` for deferred enhancements and phased improvement plan.
