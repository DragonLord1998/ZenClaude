from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from rich.console import Console

from zenclaude.docker_manager import DockerManager
from zenclaude.models import ResourceLimits, SessionMeta, STATUS_RUNNING
from zenclaude.notify import notify_session_complete
from zenclaude.paths import ensure_dirs, log_path, meta_path, session_dir, SESSIONS_DIR
from zenclaude.snapshot import create_snapshot

console = Console()


def _generate_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    hex_suffix = secrets.token_hex(3)
    return f"{timestamp}-{hex_suffix}"


class Engine:
    def __init__(self, docker: DockerManager, config: dict) -> None:
        self.docker = docker
        self.config = config

    def run_task(
        self,
        workspace: Path,
        task: str,
        limits: ResourceLimits,
        snapshot: bool = True,
        skill: str | None = None,
    ) -> SessionMeta:
        ensure_dirs()
        sid = _generate_session_id()
        session_dir(sid).mkdir(parents=True, exist_ok=True)

        meta = SessionMeta(
            id=sid,
            task=task,
            workspace=str(workspace.resolve()),
            limits=limits,
            skill=skill,
        )
        meta.started_at = datetime.now(timezone.utc).isoformat()
        meta.save(meta_path(sid))

        if snapshot:
            console.print("[bold]Creating workspace snapshot...[/bold]")
            snap = create_snapshot(workspace, sid)
            meta.snapshot_path = str(snap)
            meta.save(meta_path(sid))

        console.print("[bold]Building Docker image...[/bold]")
        image = self.docker.build_image()

        console.print("[bold]Starting container...[/bold]")
        claude_config = Path.home() / ".claude"
        container_id = self.docker.run_container(
            image=image,
            workspace=workspace.resolve(),
            task=task,
            claude_config=claude_config,
            limits=limits,
        )

        meta.set_running(container_id, image)
        meta.save(meta_path(sid))

        console.print(
            f"[bold green]Running[/bold green] session [bold]{sid}[/bold]\n"
        )

        exit_code = self._stream_and_wait(sid, container_id)

        meta.set_finished(exit_code)
        meta.save(meta_path(sid))

        self._notify(sid, meta)
        self._cleanup_container(container_id)

        return meta

    def stop_session(self, session_id: str) -> SessionMeta:
        meta = self.get_session(session_id)
        if meta.status != STATUS_RUNNING:
            raise RuntimeError(
                f"Session {session_id} is not running (status: {meta.status})"
            )
        if not meta.container_id:
            raise RuntimeError(f"Session {session_id} has no container ID")

        self.docker.stop_container(meta.container_id)
        meta.set_stopped()
        meta.save(meta_path(session_id))
        return meta

    def get_session(self, session_id: str) -> SessionMeta:
        path = meta_path(session_id)
        if not path.exists():
            raise FileNotFoundError(
                f"Session not found: {session_id}\n"
                f"No meta.json at {path}"
            )
        return SessionMeta.load(path)

    def list_sessions(self) -> list[SessionMeta]:
        if not SESSIONS_DIR.exists():
            return []
        sessions = []
        for entry in sorted(SESSIONS_DIR.iterdir(), reverse=True):
            mp = entry / "meta.json"
            if mp.exists():
                sessions.append(SessionMeta.load(mp))
        return sessions

    def stream_session_logs(
        self, session_id: str, follow: bool = False
    ) -> Iterator[str]:
        meta = self.get_session(session_id)

        if follow and meta.status == STATUS_RUNNING and meta.container_id:
            yield from self.docker.stream_logs(meta.container_id, follow=True)
            return

        path = log_path(session_id)
        if path.exists():
            yield from path.read_text().splitlines()
        elif meta.container_id:
            yield from self.docker.stream_logs(meta.container_id, follow=False)

    def _stream_and_wait(self, session_id: str, container_id: str) -> int:
        output_path = log_path(session_id)
        with open(output_path, "w") as log_file:
            for line in self.docker.stream_logs(container_id, follow=True):
                console.print(line, highlight=False, end="")
                log_file.write(line)
                log_file.flush()

        exit_code = self.docker.get_exit_code(container_id)
        return exit_code if exit_code is not None else 1

    def _notify(self, session_id: str, meta: SessionMeta) -> None:
        notifications = self.config.get("notifications", {})
        if not notifications.get("enabled", True):
            return
        notify_session_complete(session_id, meta.status, meta.task)

    def _cleanup_container(self, container_id: str) -> None:
        try:
            self.docker.remove_container(container_id)
        except Exception:
            pass
