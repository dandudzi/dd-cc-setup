# dd-cc-setup

## Rules to follow

- Check todo list before starting each step

## Project Purpose

Claude Code observability and hook behaviour lab.

- Captures and categorises all Claude tool calls (actions) into plugins/categories
- First milestone: action categorisation pipeline (capture → categorise → JSON output)
- Feeds into observability dashboards and webhook behaviour rules
- Also serves as a reusable template for all Claude Code projects

## Tech Stack

- Language: Python 3.12+
- Package manager: uv
- Linting/formatting: ruff
- Testing: pytest
- Log format: JSONL (one JSON object per line)

## Deployment

Scripts deployed alongside Claude Code hooks via `.claude/settings.local.json`.

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

## Task Management

- Use TaskCreate for multi-step work
- Set dependencies with addBlockedBy for sequential phases
- Update status to in_progress before starting each task
- Mark completed only after verification
