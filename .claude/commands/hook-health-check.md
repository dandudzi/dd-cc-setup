# Hook Health Check

Analyze all observability and token savings data. Snapshot, compare against previous, report errors and anomalies.

## Data Sources

### Hook Decisions
| File | Content |
|------|---------|
| `~/.claude/hooks/hook-events.jsonl` | Hook routing decisions: block/allow/rewrite/error with `latency_ms` |

### Token Savings (5 sources)
| Source | How to Read | What It Shows |
|--------|-------------|---------------|
| **RTK** | `rtk gain` | Per-command savings (tokens saved, efficiency %, exec time) |
| **jCodeMunch** | `~/.code-index/_genuine_savings.json` | Cumulative savings by jCodeMunch tool |
| **jDocMunch** | Same file — `by_tool` includes `mcp__jdocmunch__*` | Cumulative savings by jDocMunch tool |
| **context-mode** | `mcp__plugin_context-mode_context-mode__ctx_stats` MCP tool | Per-session context window savings |
| **Savings history** | `~/.code-index/_genuine_savings_history.jsonl` | Per-call savings timeline |

### Continuous Learning
| File | Content |
|------|---------|
| `~/.claude/homunculus/projects/*/observations.jsonl` | Per-project behavioral observations |

## Snapshot Location

`~/.claude/hooks/observability-snapshots/<YYYY-MM-DDTHH-MM-SS>/`

## Instructions

### Step 1: Gather current state

Run ALL of these in a single `ctx_execute` (shell):

```bash
SNAP_DIR="$HOME/.claude/hooks/observability-snapshots/$(date +%Y-%m-%dT%H-%M-%S)"
mkdir -p "$SNAP_DIR"

# ── Hook Events ─────────────────────────────────────────────
echo "=== HOOK EVENTS ===" > "$SNAP_DIR/summary.txt"
EVENTS_FILE="$HOME/.claude/hooks/hook-events.jsonl"
cp "$EVENTS_FILE" "$SNAP_DIR/hook-events.jsonl" 2>/dev/null
EVENT_COUNT=$(wc -l < "$EVENTS_FILE" 2>/dev/null | tr -d ' ')
echo "Total events: ${EVENT_COUNT:-0}" >> "$SNAP_DIR/summary.txt"

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== ERRORS (should be 0) ===" >> "$SNAP_DIR/summary.txt"
jq -r 'select(.event=="error") | "\(.hook): \(.detail.error) (line \(.detail.line // "?"))"' "$EVENTS_FILE" >> "$SNAP_DIR/summary.txt" 2>/dev/null
echo "(end)" >> "$SNAP_DIR/summary.txt"

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== EVENTS BY HOOK ===" >> "$SNAP_DIR/summary.txt"
jq -r '.hook' "$EVENTS_FILE" 2>/dev/null | sort | uniq -c | sort -rn >> "$SNAP_DIR/summary.txt"

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== DECISIONS ===" >> "$SNAP_DIR/summary.txt"
jq -r '[.hook, .decision] | @tsv' "$EVENTS_FILE" 2>/dev/null | sort | uniq -c | sort -rn >> "$SNAP_DIR/summary.txt"

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== SLOW HOOKS (>50ms) ===" >> "$SNAP_DIR/summary.txt"
jq -r 'select(.latency_ms > 50) | "\(.hook) \(.latency_ms)ms — \(.detail.cmd // .detail.file // .detail.ext // "")"' "$EVENTS_FILE" >> "$SNAP_DIR/summary.txt" 2>/dev/null

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== UNKNOWN BASH COMMANDS (top 20) ===" >> "$SNAP_DIR/summary.txt"
jq -r 'select(.hook=="unified-bash-router" and .event=="unknown") | .detail.cmd' "$EVENTS_FILE" 2>/dev/null | sort | uniq -c | sort -rn | head -20 >> "$SNAP_DIR/summary.txt"

echo "" >> "$SNAP_DIR/summary.txt"
echo "=== BASH ROUTES ===" >> "$SNAP_DIR/summary.txt"
jq -r 'select(.hook=="unified-bash-router") | .detail.route' "$EVENTS_FILE" 2>/dev/null | sort | uniq -c | sort -rn >> "$SNAP_DIR/summary.txt"

# ── Token Savings Report (RTK + jCodeMunch + jDocMunch + block cost) ──
REPORT_SCRIPT="$(git rev-parse --show-toplevel 2>/dev/null)/bin/token-savings-report.sh"
echo "" >> "$SNAP_DIR/summary.txt"
echo "=== TOKEN SAVINGS REPORT ===" >> "$SNAP_DIR/summary.txt"
if [ -f "$REPORT_SCRIPT" ]; then
  bash "$REPORT_SCRIPT" >> "$SNAP_DIR/summary.txt" 2>/dev/null
  bash "$REPORT_SCRIPT" -f json > "$SNAP_DIR/token-savings.json" 2>/dev/null
else
  echo "Report script not found: $REPORT_SCRIPT" >> "$SNAP_DIR/summary.txt"
fi

# ── Raw data snapshots ──
SAVINGS_FILE="$HOME/.code-index/_genuine_savings.json"
cp "$SAVINGS_FILE" "$SNAP_DIR/genuine-savings.json" 2>/dev/null
rtk gain 2>/dev/null > "$SNAP_DIR/rtk-gain.txt" || true

HISTORY_FILE="$HOME/.code-index/_genuine_savings_history.jsonl"
HISTORY_COUNT=$(wc -l < "$HISTORY_FILE" 2>/dev/null | tr -d ' ')
echo "" >> "$SNAP_DIR/summary.txt"
echo "Savings history entries: ${HISTORY_COUNT:-0}" >> "$SNAP_DIR/summary.txt"
echo "context-mode: (call ctx_stats MCP tool for session data)" >> "$SNAP_DIR/summary.txt"

echo ""
echo "Snapshot saved: $SNAP_DIR"
echo ""
cat "$SNAP_DIR/summary.txt"
```

Then ALSO call `mcp__plugin_context-mode_context-mode__ctx_stats` to get context-mode savings for the current session. Note the savings in the report.

### Step 2: Compare with previous snapshot

```bash
SNAP_BASE="$HOME/.claude/hooks/observability-snapshots"
CURRENT=$(ls -d "$SNAP_BASE"/*/ 2>/dev/null | sort | tail -1)
PREV=$(ls -d "$SNAP_BASE"/*/ 2>/dev/null | sort | tail -2 | head -1)
```

If `$PREV` exists and differs from `$CURRENT`, compare:

1. **New errors** — `event=error` in current not in previous
2. **Block rate delta** — blocks per hook increased/decreased
3. **New unknown commands** — bash commands newly appearing as unknown
4. **Latency regression** — hooks slower than before (compare p95)
5. **Missing hooks** — hooks that logged before but stopped
6. **Savings delta** — jCodeMunch/jDocMunch/RTK totals up or down
7. **New observations** — continuous learning observations since last snapshot

### Step 3: Report

```
## Hook Health Check — {timestamp}

### Status: {OK | WARNINGS | ERRORS}

### Token Savings (from `bin/token-savings-report.sh -f json` → `$SNAP_DIR/token-savings.json`)
| Tool | Tokens Saved | Calls | Efficiency |
|------|-------------|-------|------------|
| RTK | {.rtk_savings.total} | {.rtk_savings.commands} | {.rtk_savings.avg_pct}% |
| jCodeMunch | {.mcp_savings.jcodemunch} | — | — |
| jDocMunch | {.mcp_savings.jdocmunch} | — | — |
| context-mode | {from ctx_stats} | {count} | {savings ratio} |
| **Gross** | **{.totals.gross_savings}** | | |
| **Block cost** | **-{.block_cost.total_tokens}** | {.block_cost.total_blocks} blocks | |
| **Net** | **{.totals.net_savings}** | | **{.totals.efficiency_pct}%** |

### Hook Errors (should be 0)
- {list or "None"}

### Warnings
- {latency regressions}
- {new unknown commands}
- {block rate anomalies}
- {missing hooks}

### Comparison with {previous_timestamp} (if exists)
- Hook events: {before} → {after} (+{delta})
- Errors: {before} → {after}
- RTK savings: {before} → {after}
- jCodeMunch+jDocMunch savings: {before} → {after}
- New unknown commands: {list}

### Recommendations
- {actionable items}
```

## Health Criteria

| Check | OK | Warning | Error |
|-------|-----|---------|-------|
| Hook error events | 0 | — | Any `event=error` |
| Latency p95 | <50ms | 50-100ms | >100ms |
| Unknown bash rate | <20% | 20-40% | >40% |
| Block rate | Stable | >20% change | — |
| Expected hooks | All 7 logging | — | Any absent |
| RTK efficiency | >70% | 50-70% | <50% |
| Savings trend | Increasing | Flat | Decreasing |

## Expected Hooks

- `unified-read-router` — Read routing
- `unified-bash-router` — Bash routing
- `agent-gate-strict` — Agent gating
- `webfetch-block` — WebFetch blocking
- `websearch-block` — WebSearch blocking (rare)
- `grep-observe` — Grep observability
- `plugin-drift-check` — only on drift (absent = good)
