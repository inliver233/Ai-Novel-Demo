import { useCallback, useState } from "react";

import type { GenerationRun } from "../../components/writing/types";
import { ApiError, apiJson } from "../../services/apiClient";

export function useGenerationHistory(args: {
  projectId: string | undefined;
  toast: { toastError: (message: string, requestId?: string) => void };
}) {
  const { projectId, toast } = args;

  const [open, setOpen] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<GenerationRun | null>(null);

  const refreshRuns = useCallback(async () => {
    if (!projectId) return;
    setRunsLoading(true);
    try {
      const res = await apiJson<{ runs: GenerationRun[] }>(`/api/projects/${projectId}/generation_runs?limit=5`);
      setRuns(res.data.runs);
      setSelectedRun(res.data.runs[0] ?? null);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRunsLoading(false);
    }
  }, [projectId, toast]);

  const openDrawer = useCallback(() => {
    setOpen(true);
    void refreshRuns();
  }, [refreshRuns]);

  const closeDrawer = useCallback(() => setOpen(false), []);

  const selectRun = useCallback(
    async (run: GenerationRun) => {
      setSelectedRun(run);
      try {
        const res = await apiJson<{ run: GenerationRun }>(`/api/generation_runs/${run.id}`);
        setSelectedRun(res.data.run);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [toast],
  );

  return { open, openDrawer, closeDrawer, runsLoading, runs, selectedRun, refreshRuns, selectRun };
}
