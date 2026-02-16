import { useEffect, useRef } from "react";
import type { AgentNodeDetail } from "../types";
import { EventCard } from "./EventCard";

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function humanizeAgentType(agentType: string): string {
  const map: Record<string, string> = {
    "root": "Primary",
    "general-purpose": "Worker",
    "Explore": "Explorer",
    "scout-servitor": "Scout",
    "technomancer": "Technomancer",
    "servitor": "Fabricator",
    "test-servitor": "Tester",
    "Plan": "Planner",
    "Bash": "Terminal",
    "claude-code-guide": "Guide",
  };
  return map[agentType] ?? agentType.charAt(0).toUpperCase() + agentType.slice(1);
}

function agentTypeColor(agentType: string): string {
  const map: Record<string, string> = {
    "root": "#0a84ff",
    "general-purpose": "#30d158",
    "Explore": "#bf5af2",
    "scout-servitor": "#bf5af2",
    "technomancer": "#ffd60a",
    "servitor": "#30d158",
    "test-servitor": "#ff453a",
    "Plan": "#0a84ff",
    "Bash": "#30d158",
    "claude-code-guide": "#0a84ff",
  };
  return map[agentType] ?? "#636366";
}

interface EventColumnProps {
  agent: AgentNodeDetail;
  depth: number;
}

export function EventColumn({ agent, depth }: EventColumnProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(agent.events.length);

  useEffect(() => {
    if (agent.events.length > prevCountRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    prevCountRef.current = agent.events.length;
  }, [agent.events.length]);

  const color = agentTypeColor(agent.agent_type);

  return (
    <div className="event-column">
      <div className="event-column-header">
        <span
          className="agent-type-badge"
          style={{ backgroundColor: hexToRgba(color, 0.15), color }}
        >
          {humanizeAgentType(agent.agent_type)}
        </span>
        <span className="event-column-desc">{agent.description}</span>
        {depth > 0 && <span className="depth-indicator">Depth {depth}</span>}
      </div>
      <div className="event-column-body" ref={scrollRef}>
        {agent.events.map((event, i) => (
          <EventCard key={event.id} event={event} index={i} />
        ))}
        {agent.events.length === 0 && (
          <div className="event-column-empty">No events yet</div>
        )}
      </div>
    </div>
  );
}
