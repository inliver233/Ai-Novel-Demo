import type { ReactNode } from "react";

import { PersistentOutletContext } from "./persistentOutletContext";

export function PersistentOutletProvider(props: { outletKey: string; activeKey: string; children: ReactNode }) {
  return (
    <PersistentOutletContext.Provider value={{ outletKey: props.outletKey, activeKey: props.activeKey }}>
      {props.children}
    </PersistentOutletContext.Provider>
  );
}
