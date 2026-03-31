#!/usr/bin/env bash
# Temporary test hook — dumps raw PreToolUse stdin + env to inspect available fields.
# Used for task 1.5b: confirm agent_id/agent_type/CLAUDE_AGENT_NAME in subagent context.
# Remove registration from settings.local.json after inspection.
echo "---" >> /tmp/hook-stdin-agent-test.ndjson
cat >> /tmp/hook-stdin-agent-test.ndjson
env | grep -i claude >> /tmp/hook-env-agent-test.txt 2>/dev/null || true
echo "---" >> /tmp/hook-env-agent-test.txt
exit 0
