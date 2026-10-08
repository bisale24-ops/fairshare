import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { openStream } from "./api";

type Live = {
  /** every push of any kind (the header and the group list use this) */
  tick: number;
  /** pushes per group, plus reconnects: a screen about ONE group refetches only when that group changed */
  groupTicks: Record<number, number>;
  reconnects: number;
  last: { group_id?: number; kind?: string } | null;
};
const empty: Live = { tick: 0, groupTicks: {}, reconnects: 0, last: null };
const LiveCtx = createContext<Live>(empty);

/**
 * Turns server pushes into counters that screens depend on, so they refetch immediately (no polling) and only when relevant.
 * Bursts are batched for 100 ms. The server sends "hello" each time a stream connects; any hello after the first means the
 * connection dropped and came back, so events may have been missed: bump `reconnects` to refetch everything once.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Live>(empty);
  const hellos = useRef(0);
  useEffect(() => {
    let batch: { group_id?: number; kind?: string }[] = [];
    let flush: ReturnType<typeof setTimeout> | undefined;
    let clear: ReturnType<typeof setTimeout> | undefined;
    const apply = () => {
      const events = batch;
      batch = [];
      setState((s) => {
        const groupTicks = { ...s.groupTicks };
        for (const e of events) if (e.group_id != null) groupTicks[e.group_id] = (groupTicks[e.group_id] ?? 0) + 1;
        return { ...s, tick: s.tick + 1, groupTicks, last: events[events.length - 1] };
      });
      clearTimeout(clear);
      clear = setTimeout(() => setState((s) => ({ ...s, last: null })), 5000);
    };
    const close = openStream((e) => {
      if (e.type === "hello") {
        hellos.current += 1;
        if (hellos.current > 1) setState((s) => ({ ...s, tick: s.tick + 1, reconnects: s.reconnects + 1 }));
        return;
      }
      batch.push({ group_id: e.group_id, kind: e.kind });
      clearTimeout(flush);
      flush = setTimeout(apply, 100);
    });
    return () => { clearTimeout(flush); clearTimeout(clear); close(); };
  }, []);
  return <LiveCtx.Provider value={state}>{children}</LiveCtx.Provider>;
}

export const useLive = () => useContext(LiveCtx);
