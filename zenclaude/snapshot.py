from __future__ import annotations

import sys
import tarfile
from pathlib import Path

from rich.console import Console

from zenclaude.paths import ensure_dirs, snapshot_path

ALWAYS_EXCLUDE = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".eggs",
    "*.egg-info",
}

console = Console()


def create_snapshot(workspace: Path, session_id: str) -> Path:
    ensure_dirs()
    dest = snapshot_path(session_id)
    gitignore_patterns = _load_gitignore(workspace)
    file_count = 0

    with console.status("[bold cyan]Creating workspace snapshot...") as _status:
        with tarfile.open(dest, "w:gz") as tar:
            for item in sorted(workspace.rglob("*")):
                rel = item.relative_to(workspace)
                if _should_exclude(rel, gitignore_patterns):
                    continue
                tar.add(item, arcname=str(rel))
                file_count += 1

    size_mb = dest.stat().st_size / (1024 * 1024)
    console.print(
        f"  Snapshot created: {file_count} files, {size_mb:.1f} MB "
        f"[dim]({dest.name})[/dim]"
    )
    return dest


def restore_snapshot(session_id: str, target: Path) -> None:
    source = snapshot_path(session_id)
    if not source.exists():
        raise FileNotFoundError(
            f"Snapshot not found: {source}\n"
            f"Session {session_id} may not have a snapshot."
        )

    with console.status("[bold cyan]Restoring workspace from snapshot..."):
        with tarfile.open(source, "r:gz") as tar:
            if sys.version_info >= (3, 12):
                tar.extractall(path=target, filter="data")
            else:
                tar.extractall(path=target)

    console.print(f"  Workspace restored from snapshot [dim]({session_id})[/dim]")


def _load_gitignore(workspace: Path) -> list[str]:
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        return []
    patterns = []
    for line in gitignore.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _should_exclude(rel_path: Path, gitignore_patterns: list[str]) -> bool:
    parts = rel_path.parts
    for part in parts:
        if part in ALWAYS_EXCLUDE:
            return True
        for pattern in ALWAYS_EXCLUDE:
            if "*" in pattern and part.endswith(pattern.lstrip("*")):
                return True

    rel_str = str(rel_path)
    for pattern in gitignore_patterns:
        if _matches_gitignore(rel_str, parts, pattern):
            return True

    return False


def _matches_gitignore(
    rel_str: str, parts: tuple[str, ...], pattern: str
) -> bool:
    clean = pattern.rstrip("/")
    if "/" not in clean:
        return any(p == clean for p in parts)
    return rel_str.startswith(clean) or rel_str == clean
