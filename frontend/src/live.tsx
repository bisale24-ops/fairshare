import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { openStream } from "./api";

type Live = { tick: number; last: { group_id?: number; kind?: string } | null };
const LiveCtx = createContext<Live>({ tick: 0, last: null });

/** Increments `tick` on every server push, so screens refetch immediately (no polling). */
export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Live>({ tick: 0, last: null });
  useEffect(() => {
    return openStream((e) => {
      if (e.type === "hello") return;
      setState((s) => ({ tick: s.tick + 1, last: { group_id: e.group_id, kind: e.kind } }));
    });
  }, []);
  return <LiveCtx.Provider value={state}>{children}</LiveCtx.Provider>;
}

export const useLive = () => useContext(LiveCtx);
