# Plan: Traffic Categorisation → Observation → Enforcement

## What This Document Is

This is a design discussion document. We're deciding HOW traffic categorisation should work before writing any code. The user wants to see the current state, the proposed state, and discuss decisions back and forth.

---

## CURRENT STATE: How Routing Works Today

### The Hook System (16 hooks in ~/.claude/hooks/)

Every tool call fires through a chain of bash hooks. Here's what happens for each tool:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL CALL ENTERS                                  │
│                                                                     │
│  ┌─── GATE (fires for ALL tools) ──────────────────────────────┐   │
│  │ jmunch-session-gate.sh                                       │   │
│  │   Are jCodeMunch + jDocMunch indexes fresh?                  │   │
│  │     NO → SOFT DENY (up to 4 times, then auto-bypass)        │   │
│  │     YES → pass through                                       │   │
│  │   Always allows: MCP tools, Agent, ToolSearch, Task*         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│                      tool-specific                                  │
│                           │                                         │
│  ┌─── READ ─────────────────────────────────────────────────────┐   │
│  │ unified-read-router.sh                                       │   │
│  │   Allowlist check (CLAUDE.md, /dev/*, small files, retry)    │   │
│  │     Code file (.py/.js/.ts/.go/+16 more) → SOFT DENY        │   │
│  │       "Use jCodeMunch get_symbol_source"                     │   │
│  │     Doc file (.md/.rst/.txt/+7 more, ≥50 lines) → SOFT DENY│   │
│  │       "Use jDocMunch search_sections + get_section"          │   │
│  │     JSON/JSONC (≥100 lines) → SOFT DENY                     │   │
│  │       "Use context-mode ctx_execute_file"                    │   │
│  │     Everything else → ALLOW                                  │   │
│  │   RETRY PATTERN: denied once → marker set → second Read OK   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── BASH ─────────────────────────────────────────────────────┐   │
│  │ unified-bash-router.sh                                       │   │
│  │   Subshells ($() or backticks) → ALLOW (can't classify)      │   │
│  │   Git write ops → ALLOW (fast exit)                          │   │
│  │   Filesystem utils (mkdir/rm/cp/mv/touch/chmod) → ALLOW     │   │
│  │   Package mgmt (npm/pip/uv install) → ALLOW                 │   │
│  │   Inline utils (cat/jq/python -c) → ALLOW                   │   │
│  │   Output redirected (>/>>)  → ALLOW                          │   │
│  │   Everything else → RTK REWRITE (if rtk available)           │   │
│  │     RTK rewrites command for token compression               │   │
│  │     Unknown commands → ALLOW (passthrough, never blocks)     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── AGENT ────────────────────────────────────────────────────┐   │
│  │ agent-gate-strict.sh                                         │   │
│  │   Prompt missing jCodeMunch/jDocMunch instructions?          │   │
│  │     YES → SOFT DENY "Add MCP instructions to prompt"        │   │
│  │     NO → ALLOW                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── WEBFETCH ─────────────────────────────────────────────────┐   │
│  │ webfetch-block.sh → HARD DENY (exit 2, always)              │   │
│  │   "Use ctx_fetch_and_index instead"                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── WEBSEARCH ────────────────────────────────────────────────┐   │
│  │ websearch-block.sh → HARD DENY (exit 2, always)             │   │
│  │   "Use Exa, Context7, or context-mode instead"               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── GREP ─────────────────────────────────────────────────────┐   │
│  │ grep-observe.sh → OBSERVE ONLY (logs, never blocks)         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── MCP (exa/context7) ──────────────────────────────────────┐   │
│  │ mcp-observe.sh → OBSERVE ONLY (logs query, never blocks)    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  NO HOOK AT ALL:                                                    │
│  • Edit — no routing, no observation                                │
│  • Write — no routing, no observation                               │
│  • Glob — no routing, no observation                                │
│  • Skill — no routing, no observation                               │
│  • ToolSearch — exempted from gate                                  │
│  • Task* — exempted from gate                                       │
│  • Cron* — no hooks                                                 │
│  • NotebookEdit — no hooks                                          │
│  • LSP — no hooks                                                   │
│  • EnterPlanMode/ExitPlanMode — no hooks                            │
│  • EnterWorktree/ExitWorktree — no hooks                            │
│  • ALL jCodeMunch MCP tools (24 tools) — no PreToolUse hook         │
│  • ALL jDocMunch MCP tools (11 tools) — no PreToolUse hook          │
│  • ALL context-mode MCP tools (6 tools) — no PreToolUse hook        │
│                                                                     │
│  PostToolUse only:                                                  │
│  • track-genuine-savings.sh — logs jCodeMunch/jDocMunch/ctx savings │
│  • observe.sh post — logs Read/Bash/Edit/Write/Agent/Grep complete  │
│  • reindex-after-commit.sh — marks index stale after git commit     │
└─────────────────────────────────────────────────────────────────────┘
```

### What's Actually Being Decided Today

| Tool                      | Hook Decision                         | Routing To                       | Enforced?                       |
| ------------------------- | ------------------------------------- | -------------------------------- | ------------------------------- |
| Read (code file)          | SOFT DENY                             | jCodeMunch                       | YES — hook blocks first attempt |
| Read (doc ≥50 lines)      | SOFT DENY                             | jDocMunch                        | YES — hook blocks first attempt |
| Read (JSON ≥100 lines)    | SOFT DENY                             | context-mode                     | YES — hook blocks first attempt |
| Read (small/config/retry) | ALLOW                                 | native Read                      | YES — hook allows               |
| Bash (git writes/fs/pkg)  | ALLOW                                 | native Bash                      | YES — hook allows fast          |
| Bash (everything else)    | REWRITE                               | RTK-wrapped Bash                 | YES — hook rewrites cmd         |
| Agent                     | SOFT DENY if missing MCP instructions | n/a (blocks bad agents)          | YES                             |
| WebFetch                  | HARD DENY                             | context-mode ctx_fetch_and_index | YES                             |
| WebSearch                 | HARD DENY                             | Exa / Context7 / context-mode    | YES                             |
| Grep                      | OBSERVE ONLY                          | **nothing — passes through!**    | NO                              |
| Glob                      | NO HOOK                               | **nothing — passes through!**    | NO                              |
| Edit                      | NO HOOK                               | n/a (always native)              | n/a                             |
| Write                     | NO HOOK                               | n/a (always native)              | n/a                             |
| MCP tools                 | NO PreToolUse HOOK                    | n/a (already optimal?)           | NO                              |

### The Gaps (Unclassified Traffic)

1. **Grep passes through unrouted.** No hook suggests jCodeMunch `search_text`/`search_symbols` for code, or jDocMunch `search_sections` for docs. The `grep-observe.sh` just logs it.

2. **Glob passes through unrouted.** No hook suggests jCodeMunch `get_file_tree` when repo is indexed.

3. **Bash routing is INCOMPLETE.** The hook has a big allowlist (git, fs, pkg) and sends everything else to RTK. But RTK only compresses output — it doesn't redirect `grep`/`find`/`curl`/`wget` to context-mode. Those commands run native, potentially flooding context.

4. **MCP-to-MCP suboptimality is invisible.** If you use `jCodeMunch get_file_content` when `get_symbol_source` would save 90% more tokens, nothing flags it.

5. **No unified logging.** Three separate observation systems exist:
   - `observe.sh` (continuous-learning) → project-scoped observations.jsonl
   - `grep-observe.sh` → its own log
   - `mcp-observe.sh` → its own log
   - `track-genuine-savings.sh` → its own savings log
     None of these talk to each other. No single view of "what happened this session."

6. **PostToolUse blind spot.** Denied calls (Read on .py, WebFetch, WebSearch) never fire PostToolUse. The observe.sh post-hook never sees them. So observation misses the most interesting events — the ones where routing actually happened.

---

## PROPOSED: What Should Change

### The Core Idea

Add a **unified classification layer** that:

1. Sees EVERY tool call (Pre AND Post)
2. Categorises it (what tool, what file type, what action type)
3. Determines the OPTIMAL tool for that action
4. Logs whether the actual choice was optimal
5. Produces a single JSONL stream that covers everything

### What This Looks Like

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL CALL ENTERS                                  │
│                                                                     │
│  ┌─── EXISTING HOOKS (unchanged) ──────────────────────────────┐   │
│  │ Session gate, Read router, Bash router, WebFetch/Search     │   │
│  │ blocks, Agent gate — all stay as they are                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│                     (allowed or denied)                              │
│                           │                                         │
│  ┌─── NEW: UNIFIED OBSERVER (PreToolUse, runs LAST) ──────────┐   │
│  │ Fires for ALL tools (matcher: *)                            │   │
│  │                                                              │   │
│  │ 1. CLASSIFY: tool_name + tool_input → category              │   │
│  │    (Read .py → code_read, Bash grep → bash_unbounded,       │   │
│  │     Grep *.md → doc_search, WebFetch → web_blocked, etc.)   │   │
│  │                                                              │   │
│  │ 2. ROUTE: category → optimal_tool                           │   │
│  │    (code_read → jCodeMunch, doc_search → jDocMunch,         │   │
│  │     bash_unbounded → context-mode, etc.)                    │   │
│  │                                                              │   │
│  │ 3. LOG: write to single JSONL                               │   │
│  │    {tool, category, optimal_tool, was_optimal, savings_est} │   │
│  │                                                              │   │
│  │ NEVER BLOCKS — always exit 0                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── NEW: UNIFIED OBSERVER (PostToolUse, runs LAST) ─────────┐   │
│  │ Same pipeline, but now can see output_size for threshold     │   │
│  │ validation. Correlates with PreToolUse entry.                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### What the Classification Categories Are

Every tool call gets ONE category. Here's the full taxonomy:

| Category         | Trigger                                            | Optimal Tool                       | Currently Enforced?                          |
| ---------------- | -------------------------------------------------- | ---------------------------------- | -------------------------------------------- |
| `code_read`      | Read on .py/.js/.ts/.go/+22 more                   | jCodeMunch get_symbol_source       | YES (hook)                                   |
| `doc_read`       | Read on .md/.rst/.txt/+4 more, ≥50 lines           | jDocMunch get_section              | YES (hook)                                   |
| `data_read`      | Read on .json/.csv/.log/.xml/+6 more, ≥100 lines   | context-mode ctx_execute_file      | YES (hook, JSON only)                        |
| `small_read`     | Read on any small file or config                   | native Read                        | YES (hook allows)                            |
| `edit_prep_read` | Read followed by Edit on same file                 | native Read                        | YES (hook retry allows)                      |
| `code_search`    | Grep with glob matching code extensions            | jCodeMunch search_text             | **NO — gap**                                 |
| `doc_search`     | Grep with glob matching doc extensions             | jDocMunch search_sections          | **NO — gap**                                 |
| `file_discovery` | Glob on indexed repo                               | jCodeMunch get_file_tree           | **NO — gap**                                 |
| `bash_safe`      | Bash: git writes, mkdir, rm, pip install, echo     | native Bash                        | YES (hook allows)                            |
| `bash_rtk`       | Bash: git status, npm test, pytest, docker, etc.   | RTK-wrapped Bash                   | YES (hook rewrites)                          |
| `bash_unbounded` | Bash: grep/find/cat/git log producing large output | context-mode ctx_execute           | **PARTIAL — RTK wraps but doesn't redirect** |
| `bash_web`       | Bash: curl/wget                                    | context-mode ctx_fetch_and_index   | **NO — not blocked by bash hook**            |
| `bash_piped`     | Bash: anything with `\|` pipe                      | context-mode ctx_execute           | **NO — passes through**                      |
| `web_search`     | WebSearch                                          | Exa / Context7                     | YES (hard blocked)                           |
| `web_fetch`      | WebFetch                                           | context-mode ctx_fetch_and_index   | YES (hard blocked)                           |
| `agent_spawn`    | Agent                                              | n/a (gate checks MCP instructions) | YES (hook)                                   |
| `mcp_optimal`    | Any mcp\_\_\* tool call                            | already at destination             | n/a                                          |
| `passthrough`    | Edit, Write, Skill, Task*, Cron*, LSP, etc.        | native (no competition)            | n/a                                          |

### What's NEW vs Current

| Change                   | Current                                  | Proposed                                                             |
| ------------------------ | ---------------------------------------- | -------------------------------------------------------------------- |
| **Grep routing**         | Observe only, never suggests alternative | Classify by file type, log that jCodeMunch/jDocMunch would be better |
| **Glob routing**         | No hook at all                           | Classify, log that jCodeMunch get_file_tree exists                   |
| **Bash curl/wget**       | Allowed through (only RTK-wrapped)       | Classify as `bash_web`, log context-mode alternative                 |
| **Bash piped commands**  | Allowed through                          | Classify as `bash_piped`, log context-mode alternative               |
| **MCP tool calls**       | track-genuine-savings.sh logs savings    | Also classify — flag suboptimal MCP choices                          |
| **Unified log**          | 4 separate log files                     | Single JSONL with all traffic                                        |
| **Denied calls visible** | PostToolUse misses them                  | PreToolUse observer catches them                                     |

### What Does NOT Change

- All existing hooks stay exactly as they are
- No new enforcement (blocking/denying) — observation only
- Edit, Write, Skill, Task\*, etc. remain passthrough (no optimal alternative exists)
- RTK continues to rewrite Bash commands as before

---

## COMPLETE CATEGORIZATION RULES

These are ALL the routing rules needed. Every tool call matches exactly one rule. Research determined the optimal tool for each — no gaps.

### Read Rules

| #   | Matcher                                                                                                                                                                                     | Category           | Optimal Tool                                        | Savings | Enforcement                                      |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | --------------------------------------------------- | ------- | ------------------------------------------------ |
| R1  | Read, `file_path` matches `\.(py\|js\|jsx\|ts\|tsx\|go\|rs\|java\|php\|dart\|cs\|c\|cpp\|cc\|cxx\|hpp\|hh\|hxx\|h\|ex\|exs\|rb\|rake\|kt\|swift\|scala\|lua\|sh\|bash\|zsh\|pl\|r\|m\|fs)$` | `code_read`        | jCodeMunch `get_symbol_source` / `get_file_content` | 85-99%  | hook (unified-read-router)                       |
| R2  | Read, `file_path` matches `\.(md\|markdown\|mdx\|rst\|txt\|adoc\|org)$`                                                                                                                     | `doc_read`         | jDocMunch `get_section` / `search_sections`         | 97%     | hook (unified-read-router, ≥50 lines)            |
| R3  | Read, `file_path` matches `\.(json\|jsonc\|yaml\|yml\|csv\|tsv\|log\|xml\|html\|htm\|toml\|ini\|cfg)$`                                                                                      | `data_read`        | context-mode `ctx_execute_file`                     | 93%     | hook (unified-read-router, JSON ≥100 lines only) |
| R4  | Read, none of the above match                                                                                                                                                               | `passthrough_read` | native Read                                         | 0%      | none (allowed)                                   |

### Grep Rules

| #   | Matcher                                                              | Category         | Optimal Tool                                | Savings | Enforcement    |
| --- | -------------------------------------------------------------------- | ---------------- | ------------------------------------------- | ------- | -------------- |
| G1  | Grep, `glob` matches `\*\.(py\|js\|ts\|go\|java\|kt\|rs\|cpp\|c\|h)` | `code_search`    | jCodeMunch `search_text` / `search_symbols` | 77%     | **none (gap)** |
| G2  | Grep, `glob` matches `\*\.(md\|rst\|txt)`                            | `doc_search`     | jDocMunch `search_sections`                 | 97%     | **none (gap)** |
| G3  | Grep, `path` targets a code directory (indexed)                      | `code_search`    | jCodeMunch `search_text`                    | 77%     | **none (gap)** |
| G4  | Grep, no glob or non-code/doc glob                                   | `generic_search` | native Grep                                 | 0%      | none (allowed) |

### Glob Rules

| #   | Matcher                                                              | Category            | Optimal Tool               | Savings | Enforcement    |
| --- | -------------------------------------------------------------------- | ------------------- | -------------------------- | ------- | -------------- |
| GL1 | Glob, `pattern` matches code extensions (`**/*.py`, `**/*.ts`, etc.) | `code_discovery`    | jCodeMunch `get_file_tree` | 85%     | **none (gap)** |
| GL2 | Glob, any other pattern                                              | `generic_discovery` | native Glob                | 0%      | none (allowed) |

### Bash Rules (ordered by specificity — first match wins)

| #   | Matcher                                                                                                                                            | Category         | Optimal Tool                       | Savings | Enforcement                                        |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | ---------------------------------- | ------- | -------------------------------------------------- |
| B1  | Bash, `command` matches `^\s*(curl\|wget)\b`                                                                                                       | `bash_web`       | context-mode `ctx_fetch_and_index` | 95%     | **none (gap — bash router allows through to RTK)** |
| B2  | Bash, `command` contains `\|` (pipe)                                                                                                               | `bash_piped`     | context-mode `ctx_execute`         | 93%     | **none (gap)**                                     |
| B3  | Bash, `command` matches `^\s*(grep\|rg\|find\|cat\|git\s+log)\b`                                                                                   | `bash_unbounded` | context-mode `ctx_execute`         | 93%     | **none (gap — RTK wraps but doesn't redirect)**    |
| B4  | Bash, `command` matches `^\s*(git\s+(add\|commit\|push\|pull\|checkout\|branch\|stash\|merge\|tag\|remote\|fetch\|rebase\|config\|init\|clone))\b` | `bash_safe`      | native Bash                        | 0%      | hook (bash-router allows)                          |
| B5  | Bash, `command` matches `^\s*(mkdir\|rmdir\|touch\|chmod\|mv\|cp\|rm\|cd\|pwd\|which\|echo\|printf\|date\|id\|whoami\|kill\|pkill)\b`              | `bash_safe`      | native Bash                        | 0%      | hook (bash-router allows)                          |
| B6  | Bash, `command` matches `^\s*(npm\|pip\|pip3\|uv\|pnpm\|yarn)\s+(install\|ci\|add)\b`                                                              | `bash_safe`      | native Bash                        | 0%      | hook (bash-router allows)                          |
| B7  | Bash, `command` matches RTK-known commands (git status, pytest, vitest, docker, kubectl, cargo, gh, npm test, etc.)                                | `bash_rtk`       | RTK-wrapped Bash                   | 60-99%  | hook (bash-router rewrites)                        |
| B8  | Bash, none of the above                                                                                                                            | `bash_unknown`   | RTK passthrough (fail-open)        | 0%      | hook (bash-router passes through)                  |

### Blocked Tools

| #   | Matcher   | Category             | Optimal Tool                                              | Savings | Enforcement              |
| --- | --------- | -------------------- | --------------------------------------------------------- | ------- | ------------------------ |
| W1  | WebFetch  | `web_fetch_blocked`  | context-mode `ctx_fetch_and_index`                        | n/a     | hook (hard deny, exit 2) |
| W2  | WebSearch | `web_search_blocked` | Exa `web_search_exa` (general) or Context7 (library docs) | n/a     | hook (hard deny, exit 2) |

### Agent

| #   | Matcher                                | Category        | Optimal Tool                         | Savings | Enforcement              |
| --- | -------------------------------------- | --------------- | ------------------------------------ | ------- | ------------------------ |
| A1  | Agent, prompt missing MCP instructions | `agent_ungated` | n/a (block until instructions added) | n/a     | hook (agent-gate-strict) |
| A2  | Agent, prompt has MCP instructions     | `agent_ok`      | native Agent                         | 0%      | hook (allows)            |

### MCP Tools (already at destination)

| #   | Matcher                                                  | Category      | Optimal Tool    | Savings | Enforcement |
| --- | -------------------------------------------------------- | ------------- | --------------- | ------- | ----------- |
| M1  | `mcp__jcodemunch__*`                                     | `mcp_code`    | already optimal | 0%      | none        |
| M2  | `mcp__jdocmunch__*`                                      | `mcp_doc`     | already optimal | 0%      | none        |
| M3  | `mcp__plugin_context-mode_context-mode__*`               | `mcp_context` | already optimal | 0%      | none        |
| M4  | `mcp__exa__*` or `mcp__claude_ai_exa__*`                 | `mcp_search`  | already optimal | 0%      | none        |
| M5  | `mcp__context7__*` or `mcp__plugin_context7_context7__*` | `mcp_libdocs` | already optimal | 0%      | none        |

### Passthrough (no competition — always native)

| #   | Matcher                                | Category      | Optimal Tool | Enforcement |
| --- | -------------------------------------- | ------------- | ------------ | ----------- |
| P1  | Edit                                   | `passthrough` | native Edit  | none        |
| P2  | Write                                  | `passthrough` | native Write | none        |
| P3  | Skill                                  | `passthrough` | native Skill | none        |
| P4  | TaskCreate/Get/List/Update/Output/Stop | `passthrough` | native       | none        |
| P5  | CronCreate/Delete/List                 | `passthrough` | native       | none        |
| P6  | NotebookEdit                           | `passthrough` | native       | none        |
| P7  | LSP                                    | `passthrough` | native       | none        |
| P8  | EnterPlanMode/ExitPlanMode             | `passthrough` | native       | none        |
| P9  | EnterWorktree/ExitWorktree             | `passthrough` | native       | none        |
| P10 | AskUserQuestion                        | `passthrough` | native       | none        |
| P11 | ToolSearch                             | `passthrough` | native       | none        |

### Gap Reasoning: Why These Tools Are The Correct Decision

#### Gap G1-G3: Grep → jCodeMunch/jDocMunch

**Current state:** `grep-observe.sh` logs Grep calls but never blocks or redirects. Every Grep runs natively.

**Why jCodeMunch `search_text`/`search_symbols` is better for code files:**

- jCodeMunch indexes the AST. `search_symbols` finds function/class definitions by name — zero false positives. Native Grep returns every line containing the string, including comments, strings, variable names that happen to match.
- `search_text` searches cached file contents — no filesystem I/O, results grouped by file with optional context lines.
- Token savings: jCodeMunch returns ~15 tokens per symbol match (compact mode) vs Grep returning full matching lines with context. For a project-wide search, that's 77% fewer tokens (from jCodeMunch TOKEN_SAVINGS.md).
- **Precondition:** Repo must be indexed. If not indexed → native Grep is the only option.
- **Exception:** Grep with regex patterns that jCodeMunch can't handle (search_text is plain text only, no regex). Native Grep wins for regex.

**Why jDocMunch `search_sections` is better for doc files:**

- jDocMunch indexes docs by heading hierarchy. `search_sections` returns ranked section matches — conceptual search, not string matching.
- Returns section headings + summaries, not raw lines. 97% token savings (from jDocMunch SPEC.md benchmarks).
- **Precondition:** Docs must be indexed via `index_local`.
- **Exception:** Exact literal string search in docs — native Grep is more precise.

#### Gap GL1: Glob → jCodeMunch `get_file_tree`

**Current state:** No hook at all. Every Glob runs natively.

**Why jCodeMunch `get_file_tree` is better for indexed repos:**

- `get_file_tree` returns structured directory tree with file-level annotations (language, symbol count) from the index. No filesystem traversal needed.
- Supports `path_prefix` scoping to narrow results.
- Token savings: ~200k tokens for raw `find`/`ls -R` vs ~2k tokens from `get_file_tree` — 99% savings (from jCodeMunch TOKEN_SAVINGS.md).
- **Precondition:** Repo must be indexed.
- **Exception:** Glob patterns for non-code files (`**/*.json`, `**/*.yaml`) — jCodeMunch only indexes code files. Native Glob is the only option for non-code patterns.

#### Gap B1: Bash curl/wget → context-mode `ctx_fetch_and_index`

**Current state:** `unified-bash-router.sh` doesn't match curl/wget in its allowlist, so they fall through to RTK rewrite. RTK has `curl_cmd.rs` and `wget_cmd.rs` modules that compress output (70-95% savings). But the output still enters the context window.

**Why context-mode `ctx_fetch_and_index` is better:**

- `ctx_fetch_and_index` fetches the URL, converts HTML to markdown (strips scripts/styles/nav), indexes the content into FTS5, and returns only a 3072-byte preview. The full content is searchable via `ctx_search` but never enters context.
- RTK compresses curl output but it's still raw — could be HTML, JSON, binary. Context-mode understands content types and processes them appropriately.
- For HTML pages: RTK returns compressed HTML (still large). Context-mode converts to markdown and indexes — 99% savings.
- For JSON APIs: RTK does JSON schema extraction. Context-mode indexes the JSON for querying. Both are good, but context-mode keeps it out of the context window entirely.
- **Note:** context-mode's PreToolUse hook (`pretooluse.mjs`) already blocks `curl`/`wget` in Bash and redirects. But `unified-bash-router.sh` fires first and may allow the command before context-mode's hook gets a chance. The hooks are not coordinated.

#### Gap B2: Bash piped commands → context-mode `ctx_execute`

**Current state:** `unified-bash-router.sh` detects subshells (`$()` and backticks) and allows them through. But pipes (`|`) are not detected — they fall through to RTK. RTK handles chained commands but output still enters context.

**Why context-mode `ctx_execute` is better:**

- Piped commands have unbounded output by nature. `cat file.py | grep pattern` could return 0 lines or 10,000 lines.
- `ctx_execute` runs the command in a sandbox, auto-indexes output >5KB, and returns only a summary. Output never floods context.
- RTK can compress the output, but if the pipe produces 50KB, even compressed it's still significant context consumption.
- **Exception:** Simple pipes with bounded output like `echo "hello" | tr 'a-z' 'A-Z'` don't need context-mode. But we can't know output size before execution, so the safe default is context-mode for all pipes.

#### Gap B3: Bash grep/find/cat/git log → context-mode `ctx_execute`

**Current state:** These commands fall through to RTK. RTK has modules for grep (`grep_cmd.rs`, 60-80% savings), find (`find_cmd.rs`, 50-70%), cat/head/tail (`read.rs`, 40-90%), and git log (in `git.rs`, 59-85%). Output is compressed but still enters context.

**Why context-mode `ctx_execute` is better:**

- These are the classic unbounded-output commands. `grep -r "TODO" .` on a large project can return thousands of lines. Even with RTK compression (60-80%), that's still hundreds of lines in context.
- `ctx_execute` keeps ALL output in the sandbox. Returns only a summary matching your intent. 93-99% savings vs 60-80% from RTK alone.
- **Key nuance:** RTK and context-mode are not mutually exclusive. RTK rewrites the command prefix (`grep` → `rtk grep`), then context-mode could sandbox the execution. But currently they don't coordinate — RTK fires at PreToolUse and rewrites, then the command runs natively.
- **For `cat`:** `unified-bash-router.sh` explicitly allows `cat` through (it's in the inline utils allowlist). This contradicts the routing — cat on a large file should go through context-mode. The bash router's allowlist is too permissive here.

---

## EXISTING CODE (for reference)

| File                                          | Status       | What it does                                                              |
| --------------------------------------------- | ------------ | ------------------------------------------------------------------------- |
| `scripts/capture/logger.py` (187 lines)       | **COMPLETE** | Reads stdin JSON, classifies, routes, logs to JSONL. 12-field schema.     |
| `scripts/categorise/classifier.py` (77 lines) | **COMPLETE** | 4-tier resolution: exact tool → prefix → fallback → default.              |
| `scripts/categorise/router.py` (178 lines)    | **COMPLETE** | Rule matching with regex, dynamic handler import/call.                    |
| `scripts/routing/handlers.py` (20 lines)      | **3 STUBS**  | `route_read_code`, `route_read_doc`, `redirect_to_exa` — all return None. |
| `config/mappings.json` (121 lines)            | **PARTIAL**  | Has 7 routing rules. Missing: Grep, Glob, Bash curl/wget.                 |
| `~/.claude/hooks/` (16 scripts)               | **LIVE**     | Enforcement layer — the current system diagrammed above.                  |

---
