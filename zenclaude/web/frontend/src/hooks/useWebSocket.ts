import { useEffect, useRef, useState } from "react";
import type { AgentNodeDetail, SessionDetail, WSMessage } from "../types";

const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped"]);

function insertAgent(
  node: AgentNodeDetail,
  parentId: string | null,
  newAgent: AgentNodeDetail,
): AgentNodeDetail {
  if (parentId === null) return newAgent;
  if (node.id === parentId) {
    return { ...node, children: [...node.children, newAgent] };
  }
  const updatedChildren = node.children.map((child) =>
    insertAgent(child, parentId, newAgent),
  );
  return { ...node, children: updatedChildren };
}

function updateAgentStatus(
  node: AgentNodeDetail,
  agentId: string,
  status: string,
  finishedAt: string | null,
): AgentNodeDetail {
  if (node.id === agentId) {
    return {
      ...node,
      status: status as AgentNodeDetail["status"],
      finished_at: finishedAt ?? node.finished_at,
    };
  }
  const updatedChildren = node.children.map((child) =>
    updateAgentStatus(child, agentId, status, finishedAt),
  );
  return { ...node, children: updatedChildren };
}

function appendEvent(
  node: AgentNodeDetail,
  event: SessionDetail["root_agent"]["events"][number],
): AgentNodeDetail {
  if (node.id === event.agent_id) {
    return { ...node, events: [...node.events, event] };
  }
  const updatedChildren = node.children.map((child) =>
    appendEvent(child, event),
  );
  return { ...node, children: updatedChildren };
}

function updateEvent(
  node: AgentNodeDetail,
  eventId: string,
  updates: { status: string; output_preview: string; duration_ms: number | null; error: string | null },
): AgentNodeDetail {
  const eventIndex = node.events.findIndex((e) => e.id === eventId);
  if (eventIndex !== -1) {
    const updatedEvents = [...node.events];
    const existing = updatedEvents[eventIndex]!;
    updatedEvents[eventIndex] = {
      ...existing,
      status: updates.status as typeof existing.status,
      output_preview: updates.output_preview,
      duration_ms: updates.duration_ms,
      error: updates.error,
    };
    return { ...node, events: updatedEvents };
  }
  const updatedChildren = node.children.map((child) =>
    updateEvent(child, eventId, updates),
  );
  return { ...node, children: updatedChildren };
}

export function useWebSocket(sessionId: string | null): SessionDetail | null {
  const [session, setSession] = useState<SessionDetail | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionStatusRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      sessionStatusRef.current = null;
      return;
    }

    function connect() {
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${protocol}//${location.host}/api/sessions/${sessionId}/events`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const msg: WSMessage = JSON.parse(event.data);

        switch (msg.type) {
          case "initial_state":
            setSession(msg.session);
            sessionStatusRef.current = msg.session.status;
            break;

          case "agent_spawned":
            setSession((prev) => {
              if (!prev) return prev;
              const newAgent: AgentNodeDetail = {
                id: msg.agent.id,
                parent_id: msg.parent_id,
                agent_type: msg.agent.agent_type,
                description: msg.agent.description,
                status: msg.agent.status,
                started_at: null,
                finished_at: null,
                children: [],
                events: [],
                model: msg.agent.model,
              };
              return {
                ...prev,
                root_agent: insertAgent(prev.root_agent, msg.parent_id, newAgent),
              };
            });
            break;

          case "agent_status":
            setSession((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                root_agent: updateAgentStatus(
                  prev.root_agent,
                  msg.agent_id,
                  msg.status,
                  msg.finished_at,
                ),
              };
            });
            break;

          case "tool_event":
            setSession((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                root_agent: appendEvent(prev.root_agent, msg.event),
              };
            });
            break;

          case "tool_event_update":
            setSession((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                root_agent: updateEvent(prev.root_agent, msg.event_id, {
                  status: msg.status,
                  output_preview: msg.output_preview,
                  duration_ms: msg.duration_ms,
                  error: msg.error,
                }),
              };
            });
            break;

          case "session_complete":
            sessionStatusRef.current = msg.status;
            setSession((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                status: msg.status,
                total_cost_usd: msg.total_cost_usd,
                total_tokens: msg.total_tokens,
              };
            });
            break;
        }
      };

      ws.onclose = (closeEvent) => {
        if (closeEvent.code !== 1000 && !TERMINAL_STATUSES.has(sessionStatusRef.current ?? "")) {
          reconnectTimer.current = setTimeout(connect, 2000);
        }
      };
    }

    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [sessionId]);

  return session;
}
