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
