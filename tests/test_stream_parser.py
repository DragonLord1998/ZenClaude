from __future__ import annotations

import json

from zenclaude.models import AgentNode, SessionState, ToolEvent
from zenclaude.session_store import SessionStore
from zenclaude.stream_parser import StreamParser


def _make_session_state(session_id: str = "test-session") -> SessionState:
    return SessionState(
        session_id=session_id,
        task="test task",
        status="starting",
    )


def _make_parser(
    session_id: str = "test-session",
    on_change: object = None,
) -> tuple[StreamParser, SessionState]:
    state = _make_session_state(session_id)
    parser = StreamParser(state, on_change=on_change)
    return parser, state


class TestToolEvent:
    def test_to_dict_returns_all_fields(self):
        event = ToolEvent(
            id="evt-1",
            agent_id="root",
            tool_name="Read",
            summary="Read /src/main.py",
            status="complete",
            timestamp="2025-01-01T00:00:00+00:00",
            input_preview='{"file_path": "/src/main.py"}',
            output_preview="file content here",
            duration_ms=150,
            error=None,
        )
        d = event.to_dict()
        assert d["id"] == "evt-1"
        assert d["tool_name"] == "Read"
        assert d["duration_ms"] == 150
        assert d["error"] is None

    def test_to_dict_defaults(self):
        event = ToolEvent(
            id="evt-2",
            agent_id="root",
            tool_name="text",
            summary="hello",
            status="complete",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        d = event.to_dict()
        assert d["input_preview"] == ""
        assert d["output_preview"] == ""
        assert d["duration_ms"] is None


class TestAgentNode:
    def test_to_summary_dict_excludes_events(self):
        event = ToolEvent(
            id="e1", agent_id="root", tool_name="Read",
            summary="Read x", status="complete",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        node = AgentNode(
            id="root", parent_id=None, agent_type="root",
            description="root", events=[event],
        )
        d = node.to_summary_dict()
        assert "events" not in d
        assert d["event_count"] == 1

    def test_to_detail_dict_includes_events(self):
        event = ToolEvent(
            id="e1", agent_id="root", tool_name="Read",
            summary="Read x", status="complete",
            timestamp="2025-01-01T00:00:00+00:00",
        )
        node = AgentNode(
            id="root", parent_id=None, agent_type="root",
            description="root", events=[event],
        )
        d = node.to_detail_dict()
        assert len(d["events"]) == 1
        assert d["events"][0]["id"] == "e1"

    def test_recursive_children_serialization(self):
        child = AgentNode(
            id="child-1", parent_id="root",
            agent_type="servitor", description="do stuff",
        )
        root = AgentNode(
            id="root", parent_id=None, agent_type="root",
            description="root", children=[child],
        )
        d = root.to_summary_dict()
        assert len(d["children"]) == 1
        assert d["children"][0]["id"] == "child-1"


class TestSessionState:
    def test_default_root_agent(self):
        state = SessionState(
            session_id="s1", task="test", status="running",
        )
        assert state.root_agent.id == "root"
        assert state.root_agent.parent_id is None
        assert state.root_agent.agent_type == "root"

    def test_to_summary_dict(self):
        state = _make_session_state()
        d = state.to_summary_dict()
        assert d["session_id"] == "test-session"
        assert d["root_agent"]["id"] == "root"
        assert "events" not in d["root_agent"]

    def test_to_detail_dict(self):
        state = _make_session_state()
        d = state.to_detail_dict()
        assert d["session_id"] == "test-session"
        assert "events" in d["root_agent"]


class TestStreamParserSystemEvent:
    def test_init_event_sets_model_and_status(self):
        parser, state = _make_parser()
        line = json.dumps({
            "type": "system",
            "subtype": "init",
            "model": "claude-opus-4-6",
            "session_id": "real-session-id",
        })
        parser.feed_line(line)
        assert state.model == "claude-opus-4-6"
        assert state.status == "running"
        assert state.root_agent.status == "running"
        assert state.session_id == "test-session"


class TestStreamParserAssistantEvent:
    def test_text_block_creates_event(self):
        parser, state = _make_parser()
        line = json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {"type": "text", "text": "Hello, I will help you."}
                ]
            },
        })
        parser.feed_line(line)
        assert len(state.root_agent.events) == 1
        assert state.root_agent.events[0].tool_name == "text"

    def test_empty_text_block_ignored(self):
        parser, state = _make_parser()
        line = json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {"type": "text", "text": "   "}
                ]
            },
        })
        parser.feed_line(line)
        assert len(state.root_agent.events) == 0

    def test_tool_use_creates_running_event(self):
        parser, state = _make_parser()
        line = json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_read_001",
                        "name": "Read",
                        "input": {"file_path": "/src/main.py"},
                    }
                ]
            },
        })
        parser.feed_line(line)
        assert len(state.root_agent.events) == 1
        event = state.root_agent.events[0]
        assert event.id == "toolu_read_001"
        assert event.tool_name == "Read"
        assert event.status == "running"
        assert event.summary == "Read /src/main.py"

    def test_task_tool_use_creates_child_agent(self):
        parser, state = _make_parser()
        line = json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_TASK_ABC",
                        "name": "Task",
                        "input": {
                            "prompt": "Fix the auth module",
                            "subagent_type": "technomancer",
                            "description": "Fix auth",
                            "model": "opus",
                        },
                    }
                ]
            },
        })
        parser.feed_line(line)
        assert len(state.root_agent.children) == 1
        child = state.root_agent.children[0]
        assert child.id == "toolu_TASK_ABC"
        assert child.agent_type == "technomancer"
        assert child.description == "Fix auth"
        assert child.model == "opus"
        assert child.status == "running"


class TestStreamParserSubagentRouting:
    def test_subagent_messages_routed_to_child(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_TASK_ABC",
                    "name": "Task",
                    "input": {
                        "prompt": "do stuff",
                        "subagent_type": "servitor",
                        "description": "worker",
                    },
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": "toolu_TASK_ABC",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_inner_read",
                    "name": "Read",
                    "input": {"file_path": "/src/auth.py"},
                }]
            },
        }))

        child = state.root_agent.children[0]
        assert len(child.events) == 1
        assert child.events[0].id == "toolu_inner_read"
        assert child.events[0].tool_name == "Read"

    def test_nested_subagent_routing(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_TECH_1",
                    "name": "Task",
                    "input": {
                        "prompt": "plan",
                        "subagent_type": "technomancer",
                        "description": "planner",
                    },
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": "toolu_TECH_1",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_SERV_1",
                    "name": "Task",
                    "input": {
                        "prompt": "execute",
                        "subagent_type": "servitor",
                        "description": "executor",
                    },
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": "toolu_SERV_1",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_deep_read",
                    "name": "Read",
                    "input": {"file_path": "/deep/file.py"},
                }]
            },
        }))

        tech = state.root_agent.children[0]
        assert tech.id == "toolu_TECH_1"
        serv = tech.children[0]
        assert serv.id == "toolu_SERV_1"
        assert len(serv.events) == 1
        assert serv.events[0].id == "toolu_deep_read"


class TestStreamParserToolResult:
    def test_tool_result_completes_event(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_read_001",
                    "name": "Read",
                    "input": {"file_path": "/src/main.py"},
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_read_001",
                    "content": "file contents here",
                    "duration_ms": 42,
                }]
            },
        }))

        event = state.root_agent.events[0]
        assert event.status == "complete"
        assert event.output_preview == "file contents here"
        assert event.duration_ms == 42

    def test_error_result_sets_error_status(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_bash_001",
                    "name": "Bash",
                    "input": {"command": "rm -rf /"},
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_bash_001",
                    "content": "Permission denied",
                    "is_error": True,
                }]
            },
        }))

        event = state.root_agent.events[0]
        assert event.status == "error"
        assert event.error == "Permission denied"

    def test_task_result_completes_child_agent(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_TASK_X",
                    "name": "Task",
                    "input": {
                        "prompt": "do it",
                        "subagent_type": "servitor",
                        "description": "worker",
                    },
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_TASK_X",
                    "content": "Task completed successfully",
                }]
            },
        }))

        child = state.root_agent.children[0]
        assert child.status == "complete"
        assert child.finished_at is not None

    def test_list_content_in_tool_result(self):
        parser, state = _make_parser()

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_r1",
                    "name": "Read",
                    "input": {"file_path": "/x.py"},
                }]
            },
        }))

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_r1",
                    "content": [
                        {"type": "text", "text": "line 1"},
                        {"type": "text", "text": "line 2"},
                    ],
                }]
            },
        }))

        event = state.root_agent.events[0]
        assert "line 1" in event.output_preview
        assert "line 2" in event.output_preview


class TestStreamParserResultEvent:
    def test_result_event_sets_cost_and_tokens(self):
        parser, state = _make_parser()
        parser.feed_line(json.dumps({
            "type": "result",
            "cost_usd": 0.0542,
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        }))
        assert state.total_cost_usd == 0.0542
        assert state.total_tokens == 1500
        assert state.status == "completed"
        assert state.root_agent.status == "complete"


class TestStreamParserRawText:
    def test_non_json_line_creates_text_event(self):
        parser, state = _make_parser()
        parser.feed_line("Some raw output from Docker")
        assert len(state.root_agent.events) == 1
        event = state.root_agent.events[0]
        assert event.tool_name == "text"
        assert event.status == "complete"

    def test_empty_line_ignored(self):
        parser, state = _make_parser()
        parser.feed_line("")
        parser.feed_line("   ")
        assert len(state.root_agent.events) == 0


class TestStreamParserCallbacks:
    def test_on_change_fires_for_events(self):
        notifications = []

        def capture(session_id, event_type, data):
            notifications.append((session_id, event_type, data))

        parser, state = _make_parser(on_change=capture)
        parser.feed_line(json.dumps({
            "type": "system",
            "subtype": "init",
            "model": "opus",
        }))
        assert len(notifications) == 1
        assert notifications[0][1] == "system_init"

    def test_no_callback_does_not_error(self):
        parser, state = _make_parser(on_change=None)
        parser.feed_line(json.dumps({
            "type": "system",
            "subtype": "init",
            "model": "opus",
        }))


class TestSessionStore:
    def test_create_and_get_session(self):
        store = SessionStore()
        state = store.create_session("s1", "test task", "running")
        retrieved = store.get_session("s1")
        assert retrieved is not None
        assert retrieved.session_id == "s1"
        assert retrieved.task == "test task"

    def test_get_nonexistent_returns_none(self):
        store = SessionStore()
        assert store.get_session("nonexistent") is None

    def test_list_sessions_returns_in_memory(self):
        store = SessionStore()
        store.create_session("s1", "task1", "running", started_at="2025-01-02T00:00:00")
        store.create_session("s2", "task2", "running", started_at="2025-01-01T00:00:00")
        sessions = store.list_sessions()
        assert len(sessions) >= 2
        ids = [s.session_id for s in sessions]
        assert "s1" in ids
        assert "s2" in ids

    def test_register_and_notify_listener(self):
        store = SessionStore()
        received = []

        def listener(sid, etype, data):
            received.append((sid, etype, data))

        store.register_listener("s1", listener)
        store.notify_listeners("s1", "test_event", {"key": "value"})
        assert len(received) == 1
        assert received[0] == ("s1", "test_event", {"key": "value"})

    def test_unregister_listener(self):
        store = SessionStore()
        received = []

        def listener(sid, etype, data):
            received.append((sid, etype, data))

        store.register_listener("s1", listener)
        store.unregister_listener("s1", listener)
        store.notify_listeners("s1", "test_event", {})
        assert len(received) == 0

    def test_notify_no_listeners_does_not_error(self):
        store = SessionStore()
        store.notify_listeners("nonexistent", "event", {})


class TestToolSummaryBuilding:
    def test_read_summary(self):
        parser, state = _make_parser()
        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Read",
                    "input": {"file_path": "/src/app.py"},
                }]
            },
        }))
        assert state.root_agent.events[0].summary == "Read /src/app.py"

    def test_bash_summary_truncates(self):
        parser, state = _make_parser()
        long_cmd = "x" * 200
        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "t2",
                    "name": "Bash",
                    "input": {"command": long_cmd},
                }]
            },
        }))
        summary = state.root_agent.events[0].summary
        assert len(summary) <= 86  # "Bash: " + 80 chars

    def test_unknown_tool_uses_name(self):
        parser, state = _make_parser()
        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "t3",
                    "name": "CustomTool",
                    "input": {"something": "value"},
                }]
            },
        }))
        assert state.root_agent.events[0].summary == "CustomTool"


class TestFullSessionFlow:
    def test_complete_session_lifecycle(self):
        notifications = []

        def capture(sid, etype, data):
            notifications.append((sid, etype))

        parser, state = _make_parser(on_change=capture)

        parser.feed_line(json.dumps({
            "type": "system",
            "subtype": "init",
            "model": "claude-opus-4-6",
        }))
        assert state.status == "running"

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {"type": "text", "text": "I will read the file."},
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "Read",
                        "input": {"file_path": "/src/main.py"},
                    },
                ]
            },
        }))
        assert len(state.root_agent.events) == 2

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": "print('hello')",
                    "duration_ms": 10,
                }]
            },
        }))
        read_event = state.root_agent.events[1]
        assert read_event.status == "complete"
        assert read_event.duration_ms == 10

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_TASK_A",
                    "name": "Task",
                    "input": {
                        "prompt": "fix bug",
                        "subagent_type": "servitor",
                        "description": "bug fixer",
                        "model": "sonnet",
                    },
                }]
            },
        }))
        assert len(state.root_agent.children) == 1

        parser.feed_line(json.dumps({
            "type": "assistant",
            "parent_tool_use_id": "toolu_TASK_A",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_sub_edit",
                    "name": "Edit",
                    "input": {"file_path": "/src/main.py", "old_string": "x", "new_string": "y"},
                }]
            },
        }))
        child = state.root_agent.children[0]
        assert len(child.events) == 1
        assert child.events[0].tool_name == "Edit"

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": "toolu_TASK_A",
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_sub_edit",
                    "content": "Edit applied",
                }]
            },
        }))
        assert child.events[0].status == "complete"

        parser.feed_line(json.dumps({
            "type": "user",
            "parent_tool_use_id": None,
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_TASK_A",
                    "content": "Task completed",
                }]
            },
        }))
        assert child.status == "complete"

        parser.feed_line(json.dumps({
            "type": "result",
            "cost_usd": 0.15,
            "usage": {"input_tokens": 5000, "output_tokens": 2000},
        }))
        assert state.status == "completed"
        assert state.total_cost_usd == 0.15
        assert state.total_tokens == 7000

        detail = state.to_detail_dict()
        assert detail["session_id"] == "test-session"
        assert len(detail["root_agent"]["children"]) == 1
        assert len(detail["root_agent"]["events"]) == 3

        summary = state.to_summary_dict()
        assert "events" not in summary["root_agent"]
        assert summary["root_agent"]["event_count"] == 3

        event_types = [n[1] for n in notifications]
        assert "system_init" in event_types
        assert "tool_event" in event_types
        assert "tool_result" in event_types
        assert "agent_spawned" in event_types
        assert "agent_complete" in event_types
        assert "session_complete" in event_types
