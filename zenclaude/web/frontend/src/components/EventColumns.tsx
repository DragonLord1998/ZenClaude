import { useWebSocket } from "../hooks/useWebSocket";
import type { AgentNodeDetail } from "../types";
import { EventColumn } from "./EventColumn";

interface EventColumnsProps {
  sessionId: string | null;
}

interface FlatAgent {
  agent: AgentNodeDetail;
  depth: number;
}

function flattenAgentTree(node: AgentNodeDetail, depth: number = 0): FlatAgent[] {
  const result: FlatAgent[] = [{ agent: node, depth }];
  for (const child of node.children) {
    result.push(...flattenAgentTree(child, depth + 1));
  }
  return result;
}

export function EventColumns({ sessionId }: EventColumnsProps) {
  const session = useWebSocket(sessionId);

  if (!sessionId) {
    return (
      <main className="right-panel">
        <div className="empty-state">
          <div className="empty-state-title">Select a session</div>
          <p>Choose a session from the left to view its event stream.</p>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="right-panel">
        <div className="empty-state">
          <div className="empty-state-title">Connecting...</div>
        </div>
      </main>
    );
  }

  const agents = flattenAgentTree(session.root_agent);
  const isSingleAgent = agents.length === 1;

  return (
    <main className={`right-panel${isSingleAgent ? " single-column" : ""}`}>
      <div className="columns-container">
        {agents.map(({ agent, depth }) => (
          <EventColumn key={agent.id} agent={agent} depth={depth} />
        ))}
      </div>
    </main>
  );
}
