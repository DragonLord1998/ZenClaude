#!/bin/bash
set -euo pipefail

if [ -d /home/claude/.claude-host ]; then
    cp -a /home/claude/.claude-host/. /home/claude/.claude/
fi

mkdir -p /home/claude/.claude/debug /home/claude/.claude/todos

if [ -z "${TASK:-}" ]; then
    exec /bin/bash
fi

exec claude --dangerously-skip-permissions -p "$TASK" --verbose
