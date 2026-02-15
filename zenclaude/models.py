from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_STOPPED = "stopped"


@dataclass
class ResourceLimits:
    memory: str = "8g"
    cpus: str = "4"
    pids: int = 256


@dataclass
class SessionMeta:
    id: str
    task: str
    workspace: str
    status: str = STATUS_STARTING
    container_id: Optional[str] = None
    image: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    snapshot_path: Optional[str] = None
    skill: Optional[str] = None
    limits: ResourceLimits = field(default_factory=ResourceLimits)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> SessionMeta:
        limits_data = data.pop("limits", {})
        limits = ResourceLimits(**limits_data) if limits_data else ResourceLimits()
        return cls(limits=limits, **data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> SessionMeta:
        data = json.loads(path.read_text())
        return cls.from_dict(data)

    def set_running(self, container_id: str, image: str) -> None:
        self.status = STATUS_RUNNING
        self.container_id = container_id
        self.image = image
        self.started_at = datetime.now(timezone.utc).isoformat()

    def set_finished(self, exit_code: int) -> None:
        self.status = STATUS_COMPLETED if exit_code == 0 else STATUS_FAILED
        self.exit_code = exit_code
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def set_stopped(self) -> None:
        self.status = STATUS_STOPPED
        self.finished_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ToolEvent:
    id: str
    agent_id: str
    tool_name: str
    summary: str
    status: str
    timestamp: str
    input_preview: str = ""
    output_preview: str = ""
    duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "status": self.status,
            "timestamp": self.timestamp,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class AgentNode:
    id: str
    parent_id: str | None
    agent_type: str
    description: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    children: list[AgentNode] = field(default_factory=list)
    events: list[ToolEvent] = field(default_factory=list)
    model: str | None = None

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "agent_type": self.agent_type,
            "description": self.description,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "model": self.model,
            "children": [c.to_summary_dict() for c in self.children],
            "event_count": len(self.events),
        }

    def to_detail_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "agent_type": self.agent_type,
            "description": self.description,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "model": self.model,
            "children": [c.to_detail_dict() for c in self.children],
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class SessionState:
    session_id: str
    task: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    root_agent: AgentNode = field(default_factory=lambda: AgentNode(
        id="root", parent_id=None, agent_type="root", description="root agent",
    ))
    total_cost_usd: float | None = None
    total_tokens: int | None = None
    model: str | None = None

    def to_summary_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "root_agent": self.root_agent.to_summary_dict(),
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "model": self.model,
        }

    def to_detail_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "root_agent": self.root_agent.to_detail_dict(),
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "model": self.model,
        }
