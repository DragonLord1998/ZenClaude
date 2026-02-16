import type { AgentStatus } from "../types";

const STATUS_COLORS: Record<AgentStatus, string> = {
  complete: "#30d158",
  running: "#0a84ff",
  pending: "#f59e0b",
  error: "#ff453a",
};

interface StatusDiamondProps {
  status: AgentStatus;
  label: string;
  sublabel?: string;
  eventCount?: number;
  indent?: number;
}

export function StatusDiamond({ status, label, sublabel, eventCount, indent = 0 }: StatusDiamondProps) {
  const color = STATUS_COLORS[status];
  const isRunning = status === "running";

  return (
    <div
      className="status-diamond-row"
      style={{ paddingLeft: indent * 16 }}
      title={sublabel ? `${label} — ${sublabel}` : label}
    >
      <span
        className={`status-diamond${isRunning ? " pulse glow" : ""}`}
        style={{ backgroundColor: color }}
      />
      <div className="status-diamond-label">
        <span>{label}</span>
        {sublabel && <span className="status-diamond-sublabel">{sublabel}</span>}
      </div>
      {eventCount != null && eventCount > 0 && (
        <span className="status-diamond-count">{eventCount}</span>
      )}
    </div>
  );
}
