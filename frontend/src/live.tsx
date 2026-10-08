import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { openStream } from "./api";

type Live = { tick: number; last: { group_id?: number; kind?: string } | null };
const LiveCtx = createContext<Live>({ tick: 0, last: null });

/**
 * Increments `tick` on every server push, so screens refetch immediately (no polling).
 * The server sends "hello" each time a stream connects; any hello after the first means the connection dropped and
 * came back, so events may have been missed: bump the tick to refetch everything once.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Live>({ tick: 0, last: null });
  const hellos = useRef(0);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const close = openStream((e) => {
      if (e.type === "hello") {
        hellos.current += 1;
        if (hellos.current > 1) setState((s) => ({ tick: s.tick + 1, last: s.last }));
        return;
      }
      setState((s) => ({ tick: s.tick + 1, last: { group_id: e.group_id, kind: e.kind } }));
      clearTimeout(timer);
      timer = setTimeout(() => setState((s) => ({ tick: s.tick, last: null })), 5000);
    });
    return () => { clearTimeout(timer); close(); };
  }, []);
  return <LiveCtx.Provider value={state}>{children}</LiveCtx.Provider>;
}

export const useLive = () => useContext(LiveCtx);
