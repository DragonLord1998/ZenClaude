from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

SESSIONS_DIR = Path.home() / ".zenclaude" / "sessions"
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

TERMINAL_STATUSES = {"completed", "failed", "stopped"}


class RunTaskRequest(BaseModel):
    task: str
    workspace: str
    memory: Optional[str] = None
    cpus: Optional[str] = None


def create_app() -> FastAPI:
    application = FastAPI(title="ZenClaude Dashboard")
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    _templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @application.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return _templates.TemplateResponse("index.html", {"request": request})

    @application.get("/api/sessions")
    async def get_sessions() -> List[Dict]:
        return list_all_sessions()

    @application.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> Dict:
        meta = read_session_meta(session_id)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return meta

    @application.post("/api/sessions/{session_id}/stop")
    async def stop_session(session_id: str) -> Dict:
        meta = read_session_meta(session_id)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        if meta.get("status") in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail=f"Session already {meta['status']}")

        try:
            from zenclaude.docker_manager import DockerManager
        except ImportError:
            raise HTTPException(status_code=503, detail="Docker manager not available")

        container_id = meta.get("container_id")
        if not container_id:
            raise HTTPException(status_code=400, detail="Session has no container ID")

        manager = DockerManager()
        manager.stop_container(container_id)

        meta["status"] = "stopped"
        meta_path = SESSIONS_DIR / session_id / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))

        return {"status": "stopped", "session_id": session_id}

    @application.post("/api/run")
    async def run_task(body: RunTaskRequest) -> Dict:
        try:
            from zenclaude.config import load_config
            from zenclaude.docker_manager import DockerManager
            from zenclaude.engine import Engine
            from zenclaude.models import ResourceLimits
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=f"Engine not available: {exc}")

        workspace = Path(body.workspace)
        if not workspace.is_dir():
            raise HTTPException(status_code=400, detail=f"Workspace not found: {body.workspace}")

        config = load_config()
        docker_mgr = DockerManager()
        engine = Engine(docker_mgr, config)

        limits = ResourceLimits(
            memory=body.memory or "8g",
            cpus=body.cpus or "4",
        )

        def _run_in_background() -> None:
            engine.run_task(
                workspace=workspace.resolve(),
                task=body.task,
                limits=limits,
                snapshot=True,
            )

        thread = threading.Thread(target=_run_in_background, daemon=True)
        thread.start()

        await asyncio.sleep(0.5)

        sessions = list_all_sessions()
        if sessions:
            return {"session_id": sessions[0]["id"]}
        return {"session_id": "starting"}

    @application.websocket("/api/sessions/{session_id}/logs")
    async def stream_logs(websocket: WebSocket, session_id: str) -> None:
        meta = read_session_meta(session_id)
        if not meta:
            await websocket.close(code=4004, reason="Session not found")
            return

        await websocket.accept()

        log_path = SESSIONS_DIR / session_id / "output.log"
        offset = 0

        try:
            while True:
                if log_path.exists():
                    file_size = log_path.stat().st_size
                    if file_size > offset:
                        with open(log_path, "rb") as f:
                            f.seek(offset)
                            raw = f.read()
                        last_newline = raw.rfind(b"\n")
                        if last_newline != -1:
                            complete = raw[: last_newline + 1]
                            offset += len(complete)
                            await websocket.send_text(complete.decode(errors="replace"))
                        elif file_size == offset + len(raw):
                            current_meta = read_session_meta(session_id)
                            if current_meta and current_meta.get("status") in TERMINAL_STATUSES:
                                offset += len(raw)
                                await websocket.send_text(raw.decode(errors="replace"))

                current_meta = read_session_meta(session_id)
                if current_meta and current_meta.get("status") in TERMINAL_STATUSES:
                    if log_path.exists() and log_path.stat().st_size <= offset:
                        await websocket.close(code=1000, reason="Session ended")
                        return

                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            pass
        except Exception:
            try:
                await websocket.close(code=1011, reason="Internal error")
            except Exception:
                pass

    return application


def read_session_meta(session_id: str) -> Optional[Dict]:
    meta_path = SESSIONS_DIR / session_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_all_sessions() -> List[Dict]:
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for entry in SESSIONS_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta = read_session_meta(entry.name)
        if meta:
            sessions.append(meta)
    sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return sessions
