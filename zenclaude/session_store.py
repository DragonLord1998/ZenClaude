from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from zenclaude.models import AgentNode, SessionState
from zenclaude.paths import SESSIONS_DIR
from zenclaude.stream_parser import StreamParser


ListenerCallback = Callable[[str, str, dict], None]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._listeners: dict[str, list[ListenerCallback]] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        session_id: str,
        task: str,
        status: str,
        started_at: str | None = None,
    ) -> SessionState:
        root = AgentNode(
            id="root",
            parent_id=None,
            agent_type="root",
            description="root agent",
        )
        state = SessionState(
            session_id=session_id,
            task=task,
            status=status,
            started_at=started_at,
            root_agent=root,
        )
        with self._lock:
            self._sessions[session_id] = state
        return state

    def get_session(self, session_id: str) -> SessionState | None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state:
                return state

        return self._load_from_disk(session_id)

    def list_sessions(self) -> list[SessionState]:
        with self._lock:
            sessions = list(self._sessions.values())

        disk_ids = self._discover_disk_sessions()
        in_memory_ids = {s.session_id for s in sessions}

        for sid in disk_ids:
            if sid not in in_memory_ids:
                loaded = self._load_from_disk(sid)
                if loaded:
                    sessions.append(loaded)

        sessions.sort(
            key=lambda s: s.started_at or "",
            reverse=True,
        )
        return sessions

    def register_listener(self, session_id: str, callback: ListenerCallback) -> None:
        with self._lock:
            if session_id not in self._listeners:
                self._listeners[session_id] = []
            self._listeners[session_id].append(callback)

    def unregister_listener(self, session_id: str, callback: ListenerCallback) -> None:
        with self._lock:
            listeners = self._listeners.get(session_id, [])
            try:
                listeners.remove(callback)
            except ValueError:
                pass
            if not listeners and session_id in self._listeners:
                del self._listeners[session_id]

    def notify_listeners(self, session_id: str, event_type: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners.get(session_id, []))
        for callback in listeners:
            callback(session_id, event_type, data)

    def _load_from_disk(self, session_id: str) -> SessionState | None:
        meta_path = SESSIONS_DIR / session_id / "meta.json"
        if not meta_path.exists():
            return None
        try:
            raw = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        root = AgentNode(
            id="root",
            parent_id=None,
            agent_type="root",
            description="root agent",
        )
        state = SessionState(
            session_id=raw.get("id", session_id),
            task=raw.get("task", ""),
            status=raw.get("status", "unknown"),
            started_at=raw.get("started_at"),
            finished_at=raw.get("finished_at"),
            root_agent=root,
        )

        log_path = SESSIONS_DIR / session_id / "output.log"
        if log_path.exists():
            try:
                parser = StreamParser(state)
                for line in log_path.read_text().splitlines():
                    parser.feed_line(line)
            except Exception:
                pass

        return state

    def _discover_disk_sessions(self) -> list[str]:
        if not SESSIONS_DIR.exists():
            return []
        result = []
        for entry in SESSIONS_DIR.iterdir():
            if entry.is_dir() and (entry / "meta.json").exists():
                result.append(entry.name)
        return result


session_store = SessionStore()
