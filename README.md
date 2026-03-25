# dd-cc-setup

Claude Code observability and hook behaviour lab. Captures, categorises, and analyses all Claude tool calls to build observability pipelines and define webhook behaviour.

## What it does

1. **Capture** — a hook script intercepts every Claude tool call and logs it as JSONL
2. **Categorise** — a Python script reads the log and maps each action to a category/plugin using `config/mappings.json`
3. **Observe** — structured output feeds dashboards and webhook rules

## Structure

```
dd-cc-setup/
├── config/
│   └── mappings.json        # tool→category→plugin mappings
├── scripts/
│   ├── capture/             # hook logger (writes raw JSONL)
│   ├── categorise/          # categorisation script
│   └── webhooks/            # webhook handler experiments
├── tests/                   # pytest tests
├── docs/                    # architecture notes
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
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "uv run python scripts/capture/logger.py"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "uv run python scripts/capture/logger.py"}]}]
  }
}
```

## Running categorisation

```bash
uv run python scripts/categorise/categorise.py --input logs/actions.jsonl --output logs/categorised.jsonl
```

## Tests

```bash
uv run pytest
```
