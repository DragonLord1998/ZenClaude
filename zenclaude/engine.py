from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from rich.console import Console

from zenclaude.docker_manager import DockerManager
from zenclaude.models import ResourceLimits, SessionMeta, SessionState, STATUS_RUNNING
from zenclaude.notify import notify_session_complete
from zenclaude.paths import ensure_dirs, log_path, meta_path, session_dir, SESSIONS_DIR
from zenclaude.session_store import session_store
from zenclaude.snapshot import create_snapshot
from zenclaude.stream_parser import StreamParser

console = Console()


def _generate_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    hex_suffix = secrets.token_hex(3)
    return f"{timestamp}-{hex_suffix}"


def _extract_oauth_credentials() -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", "Claude Code-credentials",
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            json.loads(result.stdout.strip())
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def _reinstall_native_deps(workspace: Path) -> None:
    host_platform = platform.system()
    if host_platform == "Linux":
        return

    dirs_to_reinstall: list[Path] = []
    for node_modules in workspace.rglob("node_modules"):
        package_json = node_modules.parent / "package.json"
        if package_json.exists():
            dirs_to_reinstall.append(node_modules.parent)

    if not dirs_to_reinstall:
        return

    console.print(
        f"\n[bold]Reinstalling native dependencies for {host_platform}...[/bold]"
    )

    for project_dir in dirs_to_reinstall:
        rel = project_dir.relative_to(workspace) if project_dir != workspace else Path(".")
        console.print(f"  [dim]{rel}[/dim]")

        nm = project_dir / "node_modules"
        lock = project_dir / "package-lock.json"
        shutil.rmtree(nm, ignore_errors=True)
        if lock.exists():
            lock.unlink()

        try:
            subprocess.run(
                ["npm", "install"],
                cwd=project_dir,
                capture_output=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            console.print(f"  [yellow]Warning: npm install failed in {rel}: {exc}[/yellow]")


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
        api_key: Optional[str] = None,
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

        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            key_file = Path.home() / ".zenclaude" / "api_key"
            if key_file.exists():
                resolved_key = key_file.read_text().strip()

        oauth_creds = None
        if not resolved_key:
            oauth_creds = _extract_oauth_credentials()

        if not resolved_key and not oauth_creds:
            raise RuntimeError(
                "No API key or OAuth credentials found. Provide one via:\n"
                "  --api-key KEY\n"
                "  ANTHROPIC_API_KEY environment variable\n"
                "  ~/.zenclaude/api_key file\n"
                "  Claude Code subscription login (macOS Keychain)"
            )

        console.print("[bold]Starting container...[/bold]")
        claude_config = Path.home() / ".claude"
        container_id = self.docker.run_container(
            image=image,
            workspace=workspace.resolve(),
            task=task,
            claude_config=claude_config,
            limits=limits,
            api_key=resolved_key,
            oauth_creds=oauth_creds,
        )

        meta.set_running(container_id, image)
        meta.save(meta_path(sid))

        console.print(
            f"[bold green]Running[/bold green] session [bold]{sid}[/bold]\n"
        )

        session_state = session_store.create_session(
            session_id=sid,
            task=task,
            status="running",
            started_at=meta.started_at,
        )

        exit_code = self._stream_and_wait(sid, container_id, session_state)

        if session_state.status != "completed":
            session_state.status = "failed" if exit_code != 0 else "completed"
            session_state.finished_at = datetime.now(timezone.utc).isoformat()

        meta.set_finished(exit_code)
        meta.save(meta_path(sid))

        if exit_code == 0:
            _reinstall_native_deps(workspace.resolve())

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

    def _stream_and_wait(
        self,
        session_id: str,
        container_id: str,
        session_state: SessionState | None = None,
    ) -> int:
        child_threads: list[threading.Thread] = []

        def on_async_agent(tool_use_id: str, output_file: str) -> None:
            t = threading.Thread(
                target=self._tail_child_agent,
                args=(session_id, container_id, tool_use_id, output_file, parser),
                daemon=True,
            )
            t.start()
            child_threads.append(t)

        parser = None
        if session_state:
            parser = StreamParser(
                session_state,
                on_change=session_store.notify_listeners,
                on_async_agent=on_async_agent,
            )

        output_path = log_path(session_id)
        line_buffer = ""
        with open(output_path, "w") as log_file:
            for chunk in self.docker.stream_logs(container_id, follow=True):
                console.print(chunk, highlight=False, end="")
                log_file.write(chunk)
                log_file.flush()

                if parser:
                    line_buffer += chunk
                    while "\n" in line_buffer:
                        line, line_buffer = line_buffer.split("\n", 1)
                        parser.feed_line(line)

        if parser and line_buffer.strip():
            parser.feed_line(line_buffer)

        for t in child_threads:
            t.join(timeout=5)

        exit_code = self.docker.get_exit_code(container_id)
        return exit_code if exit_code is not None else 1

    def _tail_child_agent(
        self,
        session_id: str,
        container_id: str,
        tool_use_id: str,
        output_file: str,
        parser: StreamParser,
    ) -> None:
        child_log = session_dir(session_id) / f"child-{tool_use_id}.log"
        line_buffer = ""
        try:
            with open(child_log, "w") as f:
                for chunk in self.docker.stream_file(container_id, output_file):
                    f.write(chunk)
                    f.flush()
                    line_buffer += chunk
                    while "\n" in line_buffer:
                        line, line_buffer = line_buffer.split("\n", 1)
                        parser.feed_child_line(tool_use_id, line)
        except Exception:
            pass
        if line_buffer.strip():
            parser.feed_child_line(tool_use_id, line_buffer)

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
