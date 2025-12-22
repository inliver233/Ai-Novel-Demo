import React, { useCallback, useMemo, useState } from "react";

import clsx from "clsx";

import { ToastContext } from "./toast";
import type { ToastApi } from "./toast";

type ToastItem = {
  id: string;
  variant: "success" | "error";
  message: string;
  requestId?: string;
};

export function ToastProvider(props: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (toast: Omit<ToastItem, "id">) => {
      const id = crypto.randomUUID();
      setItems((prev) => [...prev, { id, ...toast }]);
      window.setTimeout(() => remove(id), 4500);
    },
    [remove],
  );

  const api = useMemo<ToastApi>(
    () => ({
      toastSuccess: (message, requestId) => push({ variant: "success", message, requestId }),
      toastError: (message, requestId) => push({ variant: "error", message, requestId }),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {props.children}
      <div className="fixed bottom-4 right-4 z-50 flex w-[360px] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "rounded-atelier border bg-surface p-3 shadow-sm",
              t.variant === "error" ? "border-accent" : "border-border",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-ink">{t.message}</div>
                {t.requestId ? (
                  <div className="mt-1 flex items-center gap-2 text-xs text-subtext">
                    <span className="truncate">request_id: {t.requestId}</span>
                    <button
                      className="shrink-0 rounded px-2 py-1 text-xs text-ink hover:bg-canvas"
                      onClick={async () => {
                        await navigator.clipboard.writeText(t.requestId ?? "");
                      }}
                      type="button"
                    >
                      复制
                    </button>
                  </div>
                ) : null}
              </div>
              <button
                className="rounded px-2 py-1 text-subtext hover:bg-canvas"
                onClick={() => remove(t.id)}
                type="button"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
