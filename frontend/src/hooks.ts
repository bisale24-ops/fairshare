import { useCallback, useEffect, useRef, useState } from "react";
import { useLive } from "./live";

/**
 * Load data and reload when the server pushes a change or when deps change.
 * A slower, older answer never overwrites a newer one, and data from a previous dependency
 * (e.g. the previous group) is dropped at once instead of being shown under the new id.
 */
export function useResource<T>(load: () => Promise<T>, deps: unknown[]) {
  const { tick } = useLive();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const depKey = JSON.stringify(deps);
  const lastDepKey = useRef(depKey);

  const reload = useCallback(() => {
    const id = ++latest.current;
    load()
      .then((d) => { if (id === latest.current) { setData(d); setError(null); } })
      .catch((e) => { if (id === latest.current) setError(e.message); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (lastDepKey.current !== depKey) {
      lastDepKey.current = depKey;
      setData(null);
      setError(null);
    }
    reload();
  }, [reload, tick, depKey]);
  return { data, error, reload };
}

export function useHash(): string {
  const [hash, setHash] = useState(location.hash.slice(1) || "/");
  useEffect(() => {
    const on = () => setHash(location.hash.slice(1) || "/");
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return hash;
}
