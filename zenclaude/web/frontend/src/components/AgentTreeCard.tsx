import type { AgentNodeSummary, SessionSummary } from "../types";
import { StatusDiamond } from "./StatusDiamond";

interface AgentTreeCardProps {
  session: SessionSummary;
  isSelected: boolean;
  onSelect: () => void;
  index: number;
}

function cleanTaskTitle(raw: string): string {
  let title = raw.replace(/^#+\s*/, "");
  title = title.replace(/\*\*/g, "");
  title = title.replace(/\n.*/s, "");
  if (title.length > 80) {
    title = title.slice(0, 77) + "...";
  }
  return title.trim() || raw.slice(0, 60);
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

const STATUS_DISPLAY: Record<SessionSummary["status"], string> = {
  starting: "Starting",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  stopped: "Stopped",
};

function isTrivialDescription(agentType: string, description: string): boolean {
  if (!description) return true;
  const lower = description.toLowerCase();
  const typeLower = agentType.toLowerCase();
  return lower === typeLower || lower === `${typeLower} agent`;
}

function AgentDiamonds({ agent, depth }: { agent: AgentNodeSummary; depth: number }) {
  const label = humanizeAgentType(agent.agent_type);
  const sublabel = isTrivialDescription(agent.agent_type, agent.description)
    ? undefined
    : agent.description;

  return (
    <>
      <StatusDiamond
        status={agent.status}
        label={label}
        sublabel={sublabel}
        eventCount={agent.event_count}
        indent={depth}
      />
      {agent.children.map((child) => (
        <AgentDiamonds key={child.id} agent={child} depth={depth + 1} />
      ))}
    </>
  );
}

export function AgentTreeCard({ session, isSelected, onSelect, index }: AgentTreeCardProps) {
  const statusClass = `status-${session.status}`;

  return (
    <div
      className={`session-card animate-fade-in-up${isSelected ? " selected" : ""}`}
      style={{ '--stagger-delay': `${index * 50}ms` } as React.CSSProperties}
      onClick={onSelect}
    >
      <div className="session-card-header">
        <div className="session-info">
          <div className="session-task">{cleanTaskTitle(session.task)}</div>
          <div className="session-meta">
            <span className={`status-badge ${statusClass}`}>
              <span className="status-dot" />
              {STATUS_DISPLAY[session.status]}
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
