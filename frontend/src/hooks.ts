import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

/** Phones and narrow windows: the sidebar becomes a bottom navigation bar. Keep in step with
    the `mobile:` variant in index.css. */
export const MOBILE_QUERY = "(max-width: 768px)";

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      if (typeof window.matchMedia !== "function") return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false));
}

export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY);
}

/**
 * Call `callback` now and then every `intervalMs` — but only while the page is visible. A hidden
 * tab (or a phone in the pocket) asks the server nothing; coming back asks at once.
 */
export function usePolling(callback: () => void | Promise<void>, intervalMs: number, restartKey: string | number = ""): void {
  const latest = useRef(callback);
  latest.current = callback;
  useEffect(() => {
    let timer: number | undefined;
    function stop() {
      if (timer !== undefined) window.clearInterval(timer);
      timer = undefined;
    }
    function start() {
      stop();
      void latest.current();
      timer = window.setInterval(() => void latest.current(), intervalMs);
    }
    function onVisibility() {
      if (document.visibilityState === "visible") start();
      else stop();
    }
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs, restartKey]); // a new key (for example another map level) asks at once
}
