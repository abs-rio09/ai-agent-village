import { useCallback, useSyncExternalStore } from "react";

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
