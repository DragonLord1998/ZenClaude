from __future__ import annotations

from pathlib import Path


BASE_DIR = Path.home() / ".zenclaude"
SESSIONS_DIR = BASE_DIR / "sessions"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
CONFIG_FILE = BASE_DIR / "config.toml"


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def session_dir(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def meta_path(session_id: str) -> Path:
    return session_dir(session_id) / "meta.json"


def log_path(session_id: str) -> Path:
    return session_dir(session_id) / "output.log"


def snapshot_path(session_id: str) -> Path:
    return SNAPSHOTS_DIR / f"{session_id}.tar.gz"
