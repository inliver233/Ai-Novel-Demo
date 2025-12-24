import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { useToast } from "../components/ui/toast";
import { ApiError } from "../services/apiClient";

export type ProjectDataResult<T> = {
  data: T | null;
  setData: Dispatch<SetStateAction<T | null>>;
  loading: boolean;
  refresh: () => Promise<void>;
};

export function useProjectData<T>(
  projectId: string | undefined,
  loader: (projectId: string) => Promise<T>,
): ProjectDataResult<T> {
  const toast = useToast();
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(projectId));

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const next = await loaderRef.current(projectId);
      setData(next);
    } catch (e) {
      if (e instanceof ApiError) {
        toast.toastError(`${e.message} (${e.code})`, e.requestId);
      } else {
        toast.toastError("请求失败 (UNKNOWN_ERROR)");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    if (!projectId) {
      setData(null);
      setLoading(false);
      return;
    }
    void refresh();
  }, [projectId, refresh]);

  return { data, setData, loading, refresh };
}
