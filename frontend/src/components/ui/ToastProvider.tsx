import React, { useCallback, useMemo, useState } from "react";

import clsx from "clsx";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";

import { ToastContext } from "./toast";
import type { ToastApi } from "./toast";
import { transition } from "../../lib/motion";

type ToastItem = {
  id: string;
  variant: "success" | "error";
  message: string;
  requestId?: string;
};

export function ToastProvider(props: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const reduceMotion = useReducedMotion();

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
      <LayoutGroup id="atelier-toast-stack">
        <div className="fixed bottom-4 right-4 z-50 flex w-[360px] flex-col gap-2" aria-live="polite" role="status">
          <AnimatePresence initial={false}>
            {items.map((t) => (
              <motion.div
                key={t.id}
                layout
                initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
                animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
                exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
                transition={
                  reduceMotion
                    ? { duration: 0.01 }
                    : {
                        ...transition.base,
                        layout: transition.base,
                      }
                }
                className={clsx(
                  "rounded-atelier border bg-surface/85 p-3 shadow-sm backdrop-blur",
                  t.variant === "error" ? "border-accent/60" : "border-border",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-ink">{t.message}</div>
                    {t.requestId ? (
                      <div className="mt-1 flex items-center gap-2 text-xs text-subtext">
                        <span className="truncate">request_id: {t.requestId}</span>
                        <button
                          className="btn btn-ghost px-2 py-1 text-xs"
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
                    className="btn btn-ghost btn-icon"
                    onClick={() => remove(t.id)}
                    type="button"
                    aria-label="关闭提示"
                    title="关闭"
                  >
                    ×
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </LayoutGroup>
    </ToastContext.Provider>
  );
}
