#!/bin/bash
set -euo pipefail

if [ -d /home/claude/.claude-host ]; then
    cp -a /home/claude/.claude-host/. /home/claude/.claude/
fi

mkdir -p /home/claude/.claude/debug /home/claude/.claude/todos

if [ -n "${CLAUDE_OAUTH_CREDENTIALS:-}" ]; then
    echo "$CLAUDE_OAUTH_CREDENTIALS" > /home/claude/.claude/.credentials.json
    unset CLAUDE_OAUTH_CREDENTIALS
fi

if [ -z "${TASK:-}" ]; then
    exec /bin/bash
fi

exec claude --dangerously-skip-permissions -p "$TASK" --verbose
