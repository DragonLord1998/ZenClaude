import type { SessionSummary } from "../types";
import { AgentTreeCard } from "./AgentTreeCard";

interface InstanceListProps {
  sessions: SessionSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function InstanceList({ sessions, selectedId, onSelect }: InstanceListProps) {
  if (sessions.length === 0) {
    return (
      <aside className="left-panel">
        <div className="empty-state">
          <div className="empty-state-title">No sessions yet</div>
          <p>Start a new task to get going.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="left-panel">
      {sessions.map((s) => (
        <AgentTreeCard
          key={s.session_id}
          session={s}
          isSelected={s.session_id === selectedId}
          onSelect={() => onSelect(s.session_id)}
        />
      ))}
    </aside>
  );
}
