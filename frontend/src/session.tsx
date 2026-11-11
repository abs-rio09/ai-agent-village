import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, setUnauthorizedHandler, type User, type Village } from "./api";

export type SessionState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "needs-setup" }
  | { phase: "anonymous" }
  | { phase: "authed"; user: User; village: Village };

interface SessionContextValue {
  state: SessionState;
  /** Re-read setup status, current user and village from the backend. */
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ phase: "loading" });

  const refresh = useCallback(async () => {
    try {
      const status = await api.setupStatus();
      if (!status.setup_completed) {
        setState({ phase: "needs-setup" });
        return;
      }
      const user = await api.me();
      const village = await api.village();
      setState({ phase: "authed", user, village });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState({ phase: "anonymous" });
      } else {
        setState({ phase: "error", message: error instanceof Error ? error.message : "Unexpected error" });
      }
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch (error) {
      // 401 means the session was already gone; anything else is a real failure.
      if (!(error instanceof ApiError && error.status === 401)) {
        throw error;
      }
    }
    setState({ phase: "anonymous" });
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setState((current) => (current.phase === "authed" ? { phase: "anonymous" } : current));
    });
    void refresh();
    return () => setUnauthorizedHandler(null);
  }, [refresh]);

  const value = useMemo(() => ({ state, refresh, logout }), [state, refresh, logout]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used inside <SessionProvider>");
  }
  return context;
}
