# dd-cc-setup

Claude Code observability and hook routing lab. Every Claude tool call is intercepted, classified, and logged — with routing decisions that steer work toward token-efficient tools (jCodeMunch, jDocMunch, context-mode).

## What it does

1. **Intercept** — `scripts/engine.py` runs as a PreToolUse hook for every Claude tool call
2. **Classify** — the engine walks `config/mappings.json` (v2 schema: matchers → steps) to make a routing decision
3. **Log** — every decision is written to `~/.claude/logs/actions.jsonl` as JSONL via `scripts/observe/logger.py`

Phase 1 is observe-only: the engine always exits 0 and never blocks tools. Routing enforcement comes in Phase 2.

## Structure

```
dd-cc-setup/
├── config/
│   └── mappings.json        # v2 routing config: tool → matchers[] → steps[]
├── scripts/
│   ├── engine.py            # pipeline walker (PreToolUse hook entrypoint)
│   ├── models.py            # HookInput, HookResponse, context builders
│   ├── matchers/            # matcher functions: (context) -> bool
│   ├── steps/               # step functions: (context) -> dict
│   ├── observe/             # logger: writes actions.jsonl
│   └── webhooks/            # webhook handler experiments
├── tests/                   # pytest tests
├── docs/                    # architecture notes and plans
└── pyproject.toml
```

## Setup

```bash
uv sync --extra dev
```

## Wiring hooks

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "uv run python scripts/engine.py"}]}]
  }
}
```

## Tests

```bash
uv run pytest
```
