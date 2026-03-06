import { useEffect, useRef, useState } from "react";

export type ProjectTaskLiveTask = {
  id: string;
  project_id: string;
  kind: string;
  status: string;
  attempt?: number;
  timings?: Record<string, unknown>;
};

export type ProjectTaskEventsSnapshot = {
  type: "snapshot";
  project_id: string;
  cursor: number;
  snapshot_at?: string | null;
  active_tasks: ProjectTaskLiveTask[];
};

export type ProjectTaskEventEnvelope = {
  type: "event";
  seq: number;
  project_id: string;
  task_id: string;
  kind: string;
  event_type: string;
  created_at?: string | null;
  payload?: Record<string, unknown>;
};

type StreamStatus = "idle" | "connecting" | "open" | "error";

export function useProjectTaskEvents(args: {
  projectId: string | undefined;
  enabled?: boolean;
  onSnapshot?: (snapshot: ProjectTaskEventsSnapshot) => void;
  onEvent?: (event: ProjectTaskEventEnvelope) => void;
}): { status: StreamStatus } {
  const { projectId, enabled = true, onSnapshot, onEvent } = args;
  const [liveStatus, setLiveStatus] = useState<Exclude<StreamStatus, "idle">>("connecting");
  const onSnapshotRef = useRef(onSnapshot);
  const onEventRef = useRef(onEvent);
  const eventSourceSupported = typeof window !== "undefined" && typeof window.EventSource !== "undefined";

  useEffect(() => {
    onSnapshotRef.current = onSnapshot;
  }, [onSnapshot]);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!projectId || !enabled || !eventSourceSupported) {
      return;
    }

    const source = new window.EventSource(`/api/projects/${encodeURIComponent(projectId)}/task-events/stream`);

    const handleSnapshot = (evt: MessageEvent) => {
      try {
        const payload = JSON.parse(String(evt.data || "{}")) as ProjectTaskEventsSnapshot;
        onSnapshotRef.current?.(payload);
      } catch {
        return;
      }
    };

    const handleEvent = (evt: MessageEvent) => {
      try {
        const payload = JSON.parse(String(evt.data || "{}")) as ProjectTaskEventEnvelope;
        onEventRef.current?.(payload);
      } catch {
        return;
      }
    };

    source.addEventListener("snapshot", handleSnapshot as EventListener);
    source.addEventListener("project_task", handleEvent as EventListener);
    source.onopen = () => setLiveStatus("open");
    source.onerror = () => {
      setLiveStatus((prev) => (prev === "open" ? "connecting" : "error"));
    };

    return () => {
      source.close();
    };
  }, [enabled, eventSourceSupported, projectId]);

  if (!projectId || !enabled) {
    return { status: "idle" };
  }
  if (!eventSourceSupported) {
    return { status: "error" };
  }
  return { status: liveStatus };
}
