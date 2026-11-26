import { useCallback, useEffect, useRef, useState } from "react";

/** Load data for a screen. Each screen loads its own data; no global store. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  const reload = useCallback(() => {
    const id = ++requestId.current;
    setLoading(true);
    setError(undefined);
    run()
      .then((d) => {
        if (id === requestId.current) setData(d);
      })
      .catch((e: Error) => {
        if (id === requestId.current) setError(e);
      })
      .finally(() => {
        if (id === requestId.current) setLoading(false);
      });
  }, [run]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}
