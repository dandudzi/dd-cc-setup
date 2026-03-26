# dd-cc-setup

## Rules to follow

- Check `todo.md` before starting each step — it is the **source of truth** for progress
- **NO CODE until explicitly told.** We are in the exploration/definition phase. Code is only written when the user says so.
- All plans must be written to files in `docs/plans/` and each plan **must link back** to its corresponding step in `todo.md` (e.g., `See: todo.md step 1.2`)
- Every step in `todo.md` that produces a plan must link forward to that plan file (e.g., `Plan: docs/plans/001-hook-routing.md`)
- When completing a todo step, mark it done in `todo.md` immediately

## Project Purpose

_To be defined — this is our current step. See `todo.md` step 1._

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
- `config/mappings.json` schema without updating categorisation script

## Reference Docs

- `config/mappings.json` — tool→category→plugin mappings
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

**Session-gate retry pattern (SOFT_DENY variant):** `jmunch-session-gate.sh` blocks the first Read call if the jCodeMunch/jDocMunch index is not fresh, then allows a second attempt after the index is rebuilt. This is intentional — it forces an index refresh rather than permanently denying the tool.

## Task Management

- Use TaskCreate for multi-step work
- Set dependencies with addBlockedBy for sequential phases
- Update status to in_progress before starting each task
- Mark completed only after verification

## What We Know (key facts for routing design)

**Decision factors established by extraction:**

- File extension (code vs doc vs data)
- File size in lines (threshold unknown — needs quantification)
- Bash command pattern (bounded vs unbounded output)
- Intent (read-for-analysis vs read-before-edit vs execute)
- Session state (index fresh?)
