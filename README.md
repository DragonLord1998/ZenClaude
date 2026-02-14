# ZenClaude

Run [Claude Code](https://docs.anthropic.com/en/docs/claude-code) autonomously inside Docker containers. Launch tasks, walk away, get notified when they're done.

ZenClaude wraps Claude Code in isolated Docker containers with resource limits, workspace snapshots, session management, and a live web dashboard. It reads your existing `~/.claude` configuration (API keys, skills, CLAUDE.md) without modifying it — the host config is mounted read-only and copied into the container at startup.

## Why

Claude Code is interactive by default. ZenClaude makes it fire-and-forget:

- **Isolation** — each task runs in its own container. No accidental `rm -rf` on your host.
- **Snapshots** — your workspace is snapshotted before every run. Roll back if something goes wrong.
- **Skills** — invoke Claude Code skills (`technomancer`, `rite-of-fabrication`, etc.) directly from the CLI.
- **Resource limits** — cap memory, CPU, and PIDs per container.
- **Session tracking** — every run is logged with metadata, output, and status.
- **Notifications** — macOS desktop notifications when tasks complete or fail.
- **Web dashboard** — monitor all sessions, stream logs, and launch tasks from a browser.

## Requirements

- Python 3.9+
- Docker Desktop (running)
- Claude Code installed and configured (`~/.claude` with valid API key)

## Installation

```bash
git clone https://github.com/DragonLord1998/ZenClaude.git
cd ZenClaude
pip install -e .
```

If the `zenclaude` command isn't found after install, add the Python scripts directory to your PATH:

```bash
# Check where it was installed
pip show -f zenclaude | grep bin

# Common fix for macOS
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## Quick Start

Run a plain task:

```bash
zenclaude run --task "Build a REST API with Express and TypeScript" ./my-project
```

Run with a skill:

```bash
zenclaude run --skill technomancer --task "Create a 3D solar system using Three.js" .
```

The Technomancer skill runs the full engineering lifecycle — planning, parallel implementation, testing, and code review — all autonomously inside the container.

## Usage

### `zenclaude run [WORKSPACE]`

Run a task in a Docker container.

```bash
# Plain task
zenclaude run --task "Refactor the auth module" ./my-app

# Skill + task
zenclaude run --skill technomancer --task "Add dark mode support" ./my-app

# Custom resource limits
zenclaude run --task "Train the model" --memory 16g --cpus 8 ./ml-project

# Skip the workspace snapshot
zenclaude run --task "Quick fix" --no-snapshot .
```

| Flag | Description |
|---|---|
| `-t, --task TEXT` | Task description for Claude |
| `-s, --skill TEXT` | Skill to invoke (e.g., `technomancer`) |
| `--no-snapshot` | Skip workspace snapshot before running |
| `-m, --memory TEXT` | Memory limit (default: `8g`) |
| `--cpus TEXT` | CPU limit (default: `4`) |

### `zenclaude list`

List all sessions with their status and duration.

```bash
zenclaude list
```

### `zenclaude status [SESSION_ID]`

Show detailed status for a session, or list all sessions if no ID is given.

```bash
zenclaude status 20260214-173726-0f7ce0
```

### `zenclaude logs SESSION_ID`

Show logs for a session. Use `-f` to stream in real-time.

```bash
zenclaude logs 20260214-173726-0f7ce0
zenclaude logs -f 20260214-173726-0f7ce0
```

### `zenclaude stop SESSION_ID`

Stop a running session.

```bash
zenclaude stop 20260214-173726-0f7ce0
```

### `zenclaude rollback SESSION_ID`

Restore your workspace from the snapshot taken before a session ran.

```bash
zenclaude rollback 20260214-173726-0f7ce0
```

### `zenclaude skills`

List all available skills discovered from `~/.claude/skills/` and `<workspace>/.claude/skills/`.

```bash
zenclaude skills
```

### `zenclaude dashboard`

Start the web dashboard for monitoring sessions in a browser.

```bash
zenclaude dashboard
zenclaude dashboard --port 8080 --host 0.0.0.0
```

Opens at `http://127.0.0.1:7777` by default. Features:
- Live session list with status indicators
- Real-time log streaming via WebSocket
- Launch and stop tasks from the browser

## Skills

ZenClaude discovers skills from two locations:

1. **Global:** `~/.claude/skills/` — available to all projects
2. **Local:** `<workspace>/.claude/skills/` — project-specific

Each skill is a directory (or file) containing a `SKILL.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: What this skill does
argument-hint: <task description>
---

The prompt body that gets sent to Claude Code.
```

### Built-in Skills (via Claude Code)

If you have the [Technomancer Protocol](https://github.com/DragonLord1998) skills installed in `~/.claude/skills/`, ZenClaude can invoke them:

| Skill | Description |
|---|---|
| `technomancer` | Full engineering lifecycle — plan, build, test, review |
| `rite-of-divination` | Codebase reconnaissance and analysis |
| `rite-of-schematics` | Task decomposition and planning |
| `rite-of-fabrication` | Parallel implementation with Servitors |
| `rite-of-purity` | Code review against anti-slop rules |
| `rite-of-purification` | Targeted refactoring from purity reports |
| `trial-of-machine-spirit` | End-to-end testing and verification |
| `technomancer-resume` | Resume interrupted work from manifest |

## Configuration

Optional config file at `~/.zenclaude/config.toml`:

```toml
[defaults]
memory = "8g"
cpus = "4"
pids = 256
snapshot = true

[notifications]
enabled = true
sound = true

[dashboard]
port = 7777
host = "127.0.0.1"
```

## How It Works

1. **Snapshot** — ZenClaude creates a `.tar.gz` snapshot of your workspace (respects `.gitignore`).
2. **Build** — Builds (or reuses) a Docker image with Node.js, Python, Git, and Claude Code pre-installed.
3. **Run** — Launches a container with your workspace mounted read-write and your `~/.claude` config copied in read-only.
4. **Stream** — Streams container output to your terminal and saves it to `~/.zenclaude/sessions/<id>/output.log`.
5. **Notify** — Sends a macOS notification when the task completes or fails.
6. **Cleanup** — Removes the container. Session metadata and logs persist for review.

### Security Model

- Your `~/.claude` directory is mounted **read-only** into the container. The entrypoint copies it to a writable location inside the container so Claude Code can function, but your host config is never modified.
- Workspace is mounted read-write — Claude Code needs to create and edit files.
- Containers run as a non-root `claude` user.
- Resource limits (memory, CPU, PIDs) prevent runaway processes.
- Snapshots let you roll back any workspace changes.

## Data Storage

All ZenClaude data lives under `~/.zenclaude/`:

```
~/.zenclaude/
  config.toml          # Optional configuration
  sessions/
    <session-id>/
      meta.json        # Session metadata (task, status, timestamps)
      output.log       # Full Claude Code output
  snapshots/
    <session-id>.tar.gz  # Pre-run workspace snapshot
```

## License

MIT
