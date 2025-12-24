import { createContext, useContext } from "react";

export type ConfirmOptions = {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
};

export type ChooseOptions = ConfirmOptions & {
  secondaryText: string;
  secondaryDanger?: boolean;
};

export type ConfirmChoice = "confirm" | "secondary" | "cancel";

export type ConfirmApi = {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  choose: (options: ChooseOptions) => Promise<ConfirmChoice>;
};

export const ConfirmContext = createContext<ConfirmApi | null>(null);

export function useConfirm(): ConfirmApi {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within ConfirmProvider");
  return ctx;
}
