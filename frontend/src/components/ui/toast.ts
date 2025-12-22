import { createContext, useContext } from "react";

export type ToastApi = {
  toastSuccess: (message: string, requestId?: string) => void;
  toastError: (message: string, requestId?: string) => void;
};

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
