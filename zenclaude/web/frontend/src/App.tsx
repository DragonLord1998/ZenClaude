import { useState } from "react";
import { useSessions } from "./hooks/useSessions";
import { InstanceList } from "./components/InstanceList";
import { EventColumns } from "./components/EventColumns";
import { NewTaskModal } from "./components/NewTaskModal";

export function App() {
  const { sessions, refetch } = useSessions();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div className="app-shell" style={{ background: 'radial-gradient(ellipse at 50% 0%, rgba(10, 132, 255, 0.03) 0%, transparent 70%)' }}>
      <header className="topbar glass">
        <h1 className="topbar-title">ZenClaude</h1>
        <button
          className="btn btn-primary"
          onClick={() => setModalOpen(true)}
        >
          + New Task
        </button>
      </header>

      <div className="app-layout">
        <InstanceList
          sessions={sessions}
          selectedId={selectedSessionId}
          onSelect={setSelectedSessionId}
        />
        <EventColumns sessionId={selectedSessionId} />
      </div>

      {modalOpen && (
        <NewTaskModal
          onClose={() => setModalOpen(false)}
          onCreated={(id) => {
            setModalOpen(false);
            setSelectedSessionId(id);
            refetch();
          }}
        />
      )}
    </div>
  );
}
