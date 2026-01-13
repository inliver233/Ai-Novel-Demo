import { createContext, useContext } from "react";

export type ToastApi = {
  toastSuccess: (
    message: string,
    requestId?: string,
    action?: { label: string; onClick: () => void | Promise<void> },
  ) => void;
  toastWarning: (
    message: string,
    requestId?: string,
    action?: { label: string; onClick: () => void | Promise<void> },
  ) => void;
  toastError: (
    message: string,
    requestId?: string,
    action?: { label: string; onClick: () => void | Promise<void> },
  ) => void;
};

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
