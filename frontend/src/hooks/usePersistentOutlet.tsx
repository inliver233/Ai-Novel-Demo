import { useContext } from "react";

import { PersistentOutletContext } from "./persistentOutletContext";

export function usePersistentOutletIsActive(): boolean {
  const ctx = useContext(PersistentOutletContext);
  if (!ctx) return true;
  return ctx.outletKey === ctx.activeKey;
}
