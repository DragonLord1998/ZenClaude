import { useEffect, useRef } from "react";
import type { AgentNodeDetail } from "../types";
import { StatusDiamond } from "./StatusDiamond";
import { EventCard } from "./EventCard";

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

  return (
    <div className="event-column">
      <div className="event-column-header">
        <StatusDiamond
          status={agent.status}
          label={agent.agent_type}
          indent={0}
        />
        <span className="event-column-desc">{agent.description}</span>
        {depth > 0 && <span className="event-column-depth">L{depth}</span>}
      </div>
      <div className="event-column-body" ref={scrollRef}>
        {agent.events.map((event) => (
          <EventCard key={event.id} event={event} />
        ))}
        {agent.events.length === 0 && (
          <div className="event-column-empty">No events yet</div>
        )}
      </div>
    </div>
  );
}
