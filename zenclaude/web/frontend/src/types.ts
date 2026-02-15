export interface ToolEvent {
  id: string;
  agent_id: string;
  tool_name: string;
  summary: string;
  status: "pending" | "running" | "complete" | "error";
  timestamp: string;
  input_preview: string;
  output_preview: string;
  duration_ms: number | null;
  error: string | null;
}

export interface AgentNodeSummary {
  id: string;
  agent_type: string;
  description: string;
  status: "pending" | "running" | "complete" | "error";
  children: AgentNodeSummary[];
  event_count: number;
  model: string | null;
}

export interface AgentNodeDetail {
  id: string;
  parent_id: string | null;
  agent_type: string;
  description: string;
  status: "pending" | "running" | "complete" | "error";
  started_at: string | null;
  finished_at: string | null;
  children: AgentNodeDetail[];
  events: ToolEvent[];
  model: string | null;
}

export interface SessionSummary {
  session_id: string;
  task: string;
  status: "starting" | "running" | "completed" | "failed" | "stopped";
  started_at: string | null;
  finished_at: string | null;
  root_agent: AgentNodeSummary;
  total_cost_usd: number | null;
  model: string | null;
}

export interface SessionDetail {
  session_id: string;
  task: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  root_agent: AgentNodeDetail;
  total_cost_usd: number | null;
  total_tokens: number | null;
  model: string | null;
}

export type WSMessage =
  | { type: "initial_state"; session: SessionDetail }
  | { type: "agent_spawned"; agent: AgentNodeSummary; parent_id: string | null }
  | { type: "agent_status"; agent_id: string; status: string; finished_at: string | null }
  | { type: "tool_event"; event: ToolEvent }
  | {
      type: "tool_event_update";
      event_id: string;
      status: string;
      output_preview: string;
      duration_ms: number | null;
      error: string | null;
    }
  | { type: "session_complete"; status: string; total_cost_usd: number | null; total_tokens: number | null };

export type AgentStatus = "pending" | "running" | "complete" | "error";
export type SessionStatus = "starting" | "running" | "completed" | "failed" | "stopped";

export interface SkillInfo {
  name: string;
  description: string;
  argument_hint: string;
}
