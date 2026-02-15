import type { AgentNodeSummary, SessionSummary } from "../types";
import { StatusDiamond } from "./StatusDiamond";

interface AgentTreeCardProps {
  session: SessionSummary;
  isSelected: boolean;
  onSelect: () => void;
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function AgentDiamonds({ agent, depth }: { agent: AgentNodeSummary; depth: number }) {
  return (
    <>
      <StatusDiamond
        status={agent.status}
        label={`${agent.agent_type}: ${agent.description}`}
        indent={depth}
      />
      {agent.children.map((child) => (
        <AgentDiamonds key={child.id} agent={child} depth={depth + 1} />
      ))}
    </>
  );
}

export function AgentTreeCard({ session, isSelected, onSelect }: AgentTreeCardProps) {
  const statusClass = `status-${session.status}`;

  return (
    <div
      className={`session-card${isSelected ? " selected" : ""}`}
      onClick={onSelect}
    >
      <div className="session-card-header">
        <div className="session-info">
          <div className="session-task">{session.task}</div>
          <div className="session-meta">
            <span className={`status-badge ${statusClass}`}>
              <span className="status-dot" />
              {session.status}
            </span>
            <span>{formatDuration(session.started_at, session.finished_at)}</span>
            {session.model && <span className="session-model">{session.model}</span>}
          </div>
        </div>
      </div>

      {session.root_agent && (
        <div className="agent-tree">
          <AgentDiamonds agent={session.root_agent} depth={0} />
        </div>
      )}
    </div>
  );
}
