import { createContext } from "react";

export type PersistentOutletContextValue = {
  outletKey: string;
  activeKey: string;
};

export const PersistentOutletContext = createContext<PersistentOutletContextValue | null>(null);
