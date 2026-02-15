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
  indent?: number;
}

export function StatusDiamond({ status, label, indent = 0 }: StatusDiamondProps) {
  const color = STATUS_COLORS[status];
  const isRunning = status === "running";

  return (
    <div
      className="status-diamond-row"
      style={{ paddingLeft: indent * 16 }}
      title={label}
    >
      <span
        className={`status-diamond${isRunning ? " pulse" : ""}`}
        style={{ backgroundColor: color }}
      />
      <span className="status-diamond-label">{label}</span>
    </div>
  );
}
