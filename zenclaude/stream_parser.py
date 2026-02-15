from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable

from zenclaude.models import AgentNode, SessionState, ToolEvent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _build_tool_summary(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Read":
        return f"Read {tool_input.get('file_path', '?')}"
    if tool_name == "Write":
        return f"Write {tool_input.get('file_path', '?')}"
    if tool_name == "Edit":
        return f"Edit {tool_input.get('file_path', '?')}"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash: {_truncate(cmd, 80)}"
    if tool_name == "Glob":
        return f"Glob {tool_input.get('pattern', '?')}"
    if tool_name == "Grep":
        return f"Grep {tool_input.get('pattern', '?')}"
    if tool_name == "Task":
        return f"Task: {_truncate(tool_input.get('description', tool_input.get('prompt', '?')), 80)}"
    if tool_name == "WebFetch":
        return f"WebFetch {tool_input.get('url', '?')}"
    if tool_name == "WebSearch":
        return f"WebSearch: {_truncate(tool_input.get('query', '?'), 80)}"
    return f"{tool_name}"


def _extract_input_preview(tool_input: dict) -> str:
    raw = json.dumps(tool_input, default=str)
    return _truncate(raw)


class StreamParser:
    def __init__(
        self,
        session_state: SessionState,
        on_change: Callable[[str, str, dict], None] | None = None,
    ) -> None:
        self._state = session_state
        self._on_change = on_change
        self._task_to_agent: dict[str, AgentNode] = {}
        self._agents_by_id: dict[str, AgentNode] = {"root": session_state.root_agent}
        self._events_by_tool_use_id: dict[str, ToolEvent] = {}

    @property
    def state(self) -> SessionState:
        return self._state

    def feed_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            self._handle_raw_text(stripped)
            return

        event_type = data.get("type")
        if event_type == "system":
            self._handle_system(data)
        elif event_type == "assistant":
            self._handle_assistant(data)
        elif event_type == "user":
            self._handle_user(data)
        elif event_type == "result":
            self._handle_result(data)

    def _handle_system(self, data: dict) -> None:
        subtype = data.get("subtype")
        if subtype == "init":
            self._state.model = data.get("model")
            session_id = data.get("session_id")
            if session_id:
                self._state.session_id = session_id
            self._state.root_agent.status = "running"
            self._state.root_agent.started_at = _now_iso()
            self._state.status = "running"
            self._notify("system_init", {"model": self._state.model})

    def _handle_assistant(self, data: dict) -> None:
        parent_tool_use_id = data.get("parent_tool_use_id")
        owning_agent = self._resolve_owning_agent(parent_tool_use_id)

        message = data.get("message", {})
        content_blocks = message.get("content", [])

        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                self._handle_text_block(block, owning_agent)
            elif block_type == "tool_use":
                self._handle_tool_use_block(block, owning_agent)

    def _handle_user(self, data: dict) -> None:
        parent_tool_use_id = data.get("parent_tool_use_id")
        owning_agent = self._resolve_owning_agent(parent_tool_use_id)

        message = data.get("message", {})
        content_blocks = message.get("content", [])

        for block in content_blocks:
            if block.get("type") == "tool_result":
                self._handle_tool_result(block, owning_agent)

    def _handle_result(self, data: dict) -> None:
        cost = data.get("cost_usd") or data.get("cost")
        if cost is not None:
            self._state.total_cost_usd = float(cost)

        usage = data.get("usage") or data.get("total_usage", {})
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            self._state.total_tokens = input_tokens + output_tokens

        self._state.root_agent.status = "complete"
        self._state.root_agent.finished_at = _now_iso()
        self._state.finished_at = _now_iso()
        self._state.status = "completed"
        self._notify("session_complete", {
            "cost_usd": self._state.total_cost_usd,
            "total_tokens": self._state.total_tokens,
        })

    def _handle_raw_text(self, text: str) -> None:
        event = ToolEvent(
            id=str(uuid.uuid4()),
            agent_id="root",
            tool_name="text",
            summary=_truncate(text, 80),
            status="complete",
            timestamp=_now_iso(),
            input_preview=_truncate(text),
        )
        self._state.root_agent.events.append(event)
        self._notify("tool_event", event.to_dict())

    def _handle_text_block(self, block: dict, agent: AgentNode) -> None:
        text = block.get("text", "")
        if not text.strip():
            return
        event = ToolEvent(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            tool_name="text",
            summary=_truncate(text, 80),
            status="complete",
            timestamp=_now_iso(),
            input_preview=_truncate(text),
        )
        agent.events.append(event)
        self._notify("tool_event", event.to_dict())

    def _handle_tool_use_block(self, block: dict, agent: AgentNode) -> None:
        tool_use_id = block.get("id", str(uuid.uuid4()))
        tool_name = block.get("name", "unknown")
        tool_input = block.get("input", {})

        event = ToolEvent(
            id=tool_use_id,
            agent_id=agent.id,
            tool_name=tool_name,
            summary=_build_tool_summary(tool_name, tool_input),
            status="running",
            timestamp=_now_iso(),
            input_preview=_extract_input_preview(tool_input),
        )
        agent.events.append(event)
        self._events_by_tool_use_id[tool_use_id] = event
        self._notify("tool_event", event.to_dict())

        if tool_name == "Task":
            child = AgentNode(
                id=tool_use_id,
                parent_id=agent.id,
                agent_type=tool_input.get("subagent_type", "subagent"),
                description=tool_input.get("description", tool_input.get("prompt", "")[:80]),
                status="running",
                started_at=_now_iso(),
                model=tool_input.get("model"),
            )
            agent.children.append(child)
            self._task_to_agent[tool_use_id] = child
            self._agents_by_id[tool_use_id] = child
            self._notify("agent_spawned", child.to_summary_dict())

    def _handle_tool_result(self, block: dict, agent: AgentNode) -> None:
        tool_use_id = block.get("tool_use_id")
        if not tool_use_id:
            return

        event = self._events_by_tool_use_id.get(tool_use_id)
        if not event:
            return

        is_error = block.get("is_error", False)
        content = block.get("content", "")
        if isinstance(content, list):
            text_parts = [c.get("text", "") for c in content if isinstance(c, dict)]
            content = "\n".join(text_parts)
        elif not isinstance(content, str):
            content = str(content)

        event.status = "error" if is_error else "complete"
        event.output_preview = _truncate(content)
        if is_error:
            event.error = _truncate(content, 500)

        duration = block.get("duration_ms") or block.get("durationMs")
        if duration is not None:
            event.duration_ms = int(duration)

        self._notify("tool_result", event.to_dict())

        if tool_use_id in self._task_to_agent:
            child_agent = self._task_to_agent[tool_use_id]
            child_agent.status = "error" if is_error else "complete"
            child_agent.finished_at = _now_iso()
            self._notify("agent_complete", child_agent.to_summary_dict())

    def _resolve_owning_agent(self, parent_tool_use_id: str | None) -> AgentNode:
        if parent_tool_use_id is None:
            return self._state.root_agent
        agent = self._task_to_agent.get(parent_tool_use_id)
        if agent:
            return agent
        return self._state.root_agent

    def _notify(self, event_type: str, data: dict) -> None:
        if self._on_change:
            self._on_change(self._state.session_id, event_type, data)
