import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionSummary } from "../types";

interface UseSessionsResult {
  sessions: SessionSummary[];
  loading: boolean;
  refetch: () => void;
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const data: SessionSummary[] = await res.json();
        setSessions(data);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    intervalRef.current = setInterval(fetchSessions, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchSessions]);

  return { sessions, loading, refetch: fetchSessions };
}
