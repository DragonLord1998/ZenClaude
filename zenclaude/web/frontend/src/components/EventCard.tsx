import { useState } from "react";
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

function toolColor(toolName: string): string {
  return TOOL_COLORS[toolName] ?? "#636366";
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
}

export function EventCard({ event }: EventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const color = toolColor(event.tool_name);
  const hasError = event.status === "error";
  const duration = formatDuration(event.duration_ms);

  return (
    <div
      className={`event-card${hasError ? " event-card-error" : ""} fade-in`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="event-card-row">
        <span className="tool-badge" style={{ backgroundColor: color }}>
          {event.tool_name}
        </span>
        <span className="event-summary">{event.summary}</span>
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
