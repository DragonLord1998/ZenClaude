from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from zenclaude.session_store import session_store as store

WEB_DIR = Path(__file__).parent
FRONTEND_DIST = WEB_DIR / "frontend" / "dist"
SESSIONS_DIR = Path.home() / ".zenclaude" / "sessions"
TERMINAL_STATUSES = {"completed", "failed", "stopped"}


def _read_disk_meta(session_id: str) -> dict | None:
    meta_path = SESSIONS_DIR / session_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _build_ws_message(event_type: str, data: dict) -> dict | None:
    if event_type == "tool_event":
        return {"type": "tool_event", "event": data}
    if event_type == "tool_result":
        return {
            "type": "tool_event_update",
            "event_id": data.get("id", ""),
            "status": data.get("status", "complete"),
            "output_preview": data.get("output_preview", ""),
            "duration_ms": data.get("duration_ms"),
            "error": data.get("error"),
        }
    if event_type == "agent_spawned":
        return {
            "type": "agent_spawned",
            "agent": data,
            "parent_id": data.get("parent_id"),
        }
    if event_type == "agent_complete":
        return {
            "type": "agent_status",
            "agent_id": data.get("id", ""),
            "status": data.get("status", "complete"),
            "finished_at": data.get("finished_at"),
        }
    if event_type == "session_complete":
        return {
            "type": "session_complete",
            "status": "completed",
            "total_cost_usd": data.get("cost_usd"),
            "total_tokens": data.get("total_tokens"),
        }
    return None


def create_app() -> FastAPI:
    application = FastAPI(title="ZenClaude Dashboard")

    @application.get("/api/sessions")
    async def get_sessions() -> list[dict]:
        return [s.to_summary_dict() for s in store.list_sessions()]

    @application.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        session = store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return session.to_detail_dict()

    @application.post("/api/sessions/{session_id}/stop")
    async def stop_session(session_id: str) -> dict:
        disk_meta = _read_disk_meta(session_id)
        session = store.get_session(session_id)

        if not disk_meta and not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        status = session.status if session else disk_meta.get("status")
        if status in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail=f"Session already {status}")

        try:
            from zenclaude.docker_manager import DockerManager
        except ImportError:
            raise HTTPException(status_code=503, detail="Docker manager not available")

        container_id = disk_meta.get("container_id") if disk_meta else None
        if not container_id:
            raise HTTPException(status_code=400, detail="Session has no container ID")

        manager = DockerManager()
        manager.stop_container(container_id)

        if disk_meta:
            disk_meta["status"] = "stopped"
            disk_meta["finished_at"] = datetime.now(timezone.utc).isoformat()
            meta_path = SESSIONS_DIR / session_id / "meta.json"
            meta_path.write_text(json.dumps(disk_meta, indent=2))

        if session:
            session.status = "stopped"
            session.finished_at = datetime.now(timezone.utc).isoformat()

        return {"status": "stopped", "session_id": session_id}

    @application.get("/api/browse")
    async def browse_dirs(prefix: str = "") -> list[dict]:
        if not prefix:
            prefix = str(Path.home())
        p = Path(prefix)
        if p.is_dir():
            parent = p
            partial = ""
        else:
            parent = p.parent
            partial = p.name.lower()
        if not parent.is_dir():
            return []
        results = []
        try:
            for entry in sorted(parent.iterdir()):
                if entry.name.startswith("."):
                    continue
                if not entry.is_dir():
                    continue
                if partial and not entry.name.lower().startswith(partial):
                    continue
                results.append({"name": entry.name, "path": str(entry)})
                if len(results) >= 20:
                    break
        except PermissionError:
            pass
        return results

    @application.get("/api/resolve")
    async def resolve_workspace(name: str) -> list[dict]:
        home = Path.home()
        search_roots = [
            home,
            home / "Desktop",
            home / "Documents",
            home / "Developer",
            home / "Projects",
            home / "code",
            home / "dev",
            home / "repos",
            home / "src",
            home / "work",
        ]
        results = []
        seen: set[str] = set()
        for root in search_roots:
            if not root.is_dir():
                continue
            candidate = root / name
            if candidate.is_dir() and str(candidate) not in seen:
                results.append({"name": name, "path": str(candidate)})
                seen.add(str(candidate))
        return results

    @application.get("/api/skills")
    async def get_skills(workspace: str) -> list[dict]:
        from zenclaude.skills import discover_skills

        ws = Path(workspace)
        if not ws.is_dir():
            raise HTTPException(status_code=400, detail=f"Workspace not found: {workspace}")
        available = discover_skills(ws)
        return [
            {"name": s.name, "description": s.description, "argument_hint": s.argument_hint}
            for s in available.values()
        ]

    @application.post("/api/run")
    async def run_task(
        task: str = Form(...),
        workspace: str = Form(...),
        memory: str = Form("8g"),
        cpus: str = Form("4"),
        skill: str = Form(""),
        documents: list[UploadFile] = File(default=[]),
    ) -> dict:
        try:
            from zenclaude.config import load_config
            from zenclaude.docker_manager import DockerManager
            from zenclaude.engine import Engine
            from zenclaude.models import ResourceLimits
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=f"Engine not available: {exc}")

        ws = Path(workspace)
        if not ws.is_dir():
            raise HTTPException(status_code=400, detail=f"Workspace not found: {workspace}")

        current_task = task

        docs = [d for d in documents if d.filename]
        if docs:
            context_dir = ws / ".zenclaude-context"
            context_dir.mkdir(parents=True, exist_ok=True)
            filenames = []
            for doc in docs:
                (context_dir / doc.filename).write_bytes(await doc.read())
                filenames.append(doc.filename)
            listing = "\n".join(
                f"- /workspace/.zenclaude-context/{name}" for name in filenames
            )
            current_task = f"Context documents:\n{listing}\n\n{current_task}"

        skill_name = None
        if skill.strip():
            from zenclaude.skills import discover_skills, expand_skill

            available = discover_skills(ws)
            if skill not in available:
                raise HTTPException(status_code=400, detail=f"Unknown skill: {skill}")
            current_task = expand_skill(available[skill], current_task)
            skill_name = skill

        final_task = current_task

        config = load_config()
        docker_mgr = DockerManager()
        engine = Engine(docker_mgr, config)

        limits = ResourceLimits(
            memory=memory,
            cpus=cpus,
        )

        def _run_in_background() -> None:
            engine.run_task(
                workspace=ws.resolve(),
                task=final_task,
                limits=limits,
                snapshot=True,
                skill=skill_name,
            )

        thread = threading.Thread(target=_run_in_background, daemon=True)
        thread.start()

        await asyncio.sleep(0.5)

        sessions = store.list_sessions()
        if sessions:
            return {"session_id": sessions[0].session_id}
        return {"session_id": "starting"}

    @application.websocket("/api/sessions/{session_id}/events")
    async def stream_events(websocket: WebSocket, session_id: str) -> None:
        session = store.get_session(session_id)
        if not session:
            await websocket.close(code=4004, reason="Session not found")
            return

        await websocket.accept()
        await websocket.send_json({"type": "initial_state", "session": session.to_detail_dict()})

        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(sid: str, event_type: str, data: dict) -> None:
            msg = _build_ws_message(event_type, data)
            if msg:
                loop.call_soon_threadsafe(queue.put_nowait, msg)

        store.register_listener(session_id, on_event)
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
                if event.get("type") == "session_complete":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            store.unregister_listener(session_id, on_event)

    if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @application.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(str(index), media_type="text/html")

    return application
