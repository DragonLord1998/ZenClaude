import { type ReactNode, useState } from "react";
import type { ToolEvent } from "../types";

const TOOL_COLORS: Record<string, string> = {
  Read: "#0a84ff",
  Glob: "#0a84ff",
  Grep: "#0a84ff",
  Edit: "#f59e0b",
  Write: "#f59e0b",
  Bash: "#30d158",
  Task: "#bf5af2",
  WebFetch: "#bf5af2",
  WebSearch: "#bf5af2",
};

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function toolColor(toolName: string): string {
  return TOOL_COLORS[toolName] ?? "#636366";
}

function humanizeToolName(toolName: string): string {
  const map: Record<string, string> = {
    "Read": "Read",
    "Write": "Write",
    "Edit": "Edit",
    "Glob": "Search",
    "Grep": "Grep",
    "Bash": "Terminal",
    "Task": "Agent",
    "WebFetch": "Fetch",
    "WebSearch": "Search",
    "TodoWrite": "Todo",
    "NotebookEdit": "Notebook",
  };
  return map[toolName] ?? toolName;
}

function toolBadgeStyle(toolName: string): React.CSSProperties {
  const hex = toolColor(toolName);
  return { backgroundColor: hexToRgba(hex, 0.15), color: hex };
}

const FILE_PATH_RE = /\/[\w./+-]+/;

function renderSummary(summary: string): ReactNode {
  const match = FILE_PATH_RE.exec(summary);
  if (!match) return summary;

  const path = match[0];
  const lastSlash = path.lastIndexOf("/");
  const filename = path.slice(lastSlash + 1);
  const pathWithoutFile = path.slice(0, lastSlash + 1);

  const before = summary.slice(0, match.index);
  const after = summary.slice(match.index + path.length);

  return (
    <>
      {before}{pathWithoutFile}<strong>{filename}</strong>{after}
    </>
  );
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

interface EventCardProps {
  event: ToolEvent;
  index: number;
}

export function EventCard({ event, index }: EventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const hasError = event.status === "error";
  const duration = formatDuration(event.duration_ms);
  const staggerDelay = Math.min(index * 30, 300);

  return (
    <div
      className={`event-card${hasError ? " event-card-error" : ""} animate-fade-in-up`}
      style={{ "--stagger-delay": `${staggerDelay}ms` } as React.CSSProperties}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="event-card-row">
        <span className="tool-badge" style={toolBadgeStyle(event.tool_name)}>
          {humanizeToolName(event.tool_name)}
        </span>
        <span className="event-summary">{renderSummary(event.summary)}</span>
        {duration && <span className="duration-badge">{duration}</span>}
      </div>

      {hasError && event.error && (
        <div className="event-error">{event.error}</div>
      )}

      {expanded && (
        <div className="event-detail">
          {event.input_preview && (
            <div className="event-preview">
              <div className="event-preview-label">Input</div>
              <pre className="event-preview-content">{event.input_preview}</pre>
            </div>
          )}
          {event.output_preview && (
            <div className="event-preview">
              <div className="event-preview-label">Output</div>
              <pre className="event-preview-content">{event.output_preview}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
