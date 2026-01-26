import { useEffect, useMemo, useRef } from "react";

type AutoSaveOptions<T> = {
  enabled?: boolean;
  dirty: boolean;
  saveOnIdle?: boolean;
  delayMs?: number;
  getSnapshot: () => T | null;
  onSave: (snapshot: T) => void | Promise<void>;
  deps?: unknown[];
  flushOnUnmount?: boolean;
};

export type AutoSaveController = {
  cancel: () => void;
  flush: () => void;
};

export function useAutoSave<T>(options: AutoSaveOptions<T>): AutoSaveController {
  const {
    enabled = true,
    dirty,
    saveOnIdle = false,
    delayMs = 1000,
    getSnapshot,
    onSave,
    deps = [],
    flushOnUnmount = true,
  } = options;

  const getSnapshotRef = useRef(getSnapshot);
  const onSaveRef = useRef(onSave);
  const dirtyRef = useRef(dirty);
  const enabledRef = useRef(enabled);
  const lastSnapshotRef = useRef<T | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    getSnapshotRef.current = getSnapshot;
  }, [getSnapshot]);

  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  useEffect(() => {
    dirtyRef.current = dirty;
    enabledRef.current = enabled;
    if (!enabled || !dirty || !saveOnIdle) {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [dirty, enabled, saveOnIdle]);

  const controller = useMemo<AutoSaveController>(() => {
    const cancel = () => {
      if (timerRef.current === null) return;
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
    const flush = () => {
      cancel();
      if (!enabledRef.current || !dirtyRef.current) return;
      const snapshot = getSnapshotRef.current();
      if (snapshot == null) return;
      lastSnapshotRef.current = snapshot;
      void onSaveRef.current(snapshot);
    };
    return { cancel, flush };
  }, []);

  useEffect(() => {
    if (!saveOnIdle) return;
    if (!enabled || !dirty) return;
    const snapshot = getSnapshotRef.current();
    if (snapshot == null) return;
    lastSnapshotRef.current = snapshot;

    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      const snap = lastSnapshotRef.current;
      if (snap == null) return;
      void onSaveRef.current(snap);
    }, delayMs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveOnIdle, enabled, dirty, delayMs, ...deps]);

  useEffect(() => {
    return () => {
      if (!flushOnUnmount) return;
      controller.flush();
    };
  }, [controller, flushOnUnmount]);

  return controller;
}
