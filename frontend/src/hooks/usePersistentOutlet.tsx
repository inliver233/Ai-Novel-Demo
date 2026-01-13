import { createContext, useContext } from "react";

type PersistentOutletContextValue = {
  outletKey: string;
  activeKey: string;
};

const PersistentOutletContext = createContext<PersistentOutletContextValue | null>(null);

export function PersistentOutletProvider(props: {
  outletKey: string;
  activeKey: string;
  children: React.ReactNode;
}) {
  return (
    <PersistentOutletContext.Provider value={{ outletKey: props.outletKey, activeKey: props.activeKey }}>
      {props.children}
    </PersistentOutletContext.Provider>
  );
}

export function usePersistentOutletIsActive(): boolean {
  const ctx = useContext(PersistentOutletContext);
  if (!ctx) return true;
  return ctx.outletKey === ctx.activeKey;
}

