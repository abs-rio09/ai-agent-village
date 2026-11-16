// How many approval requests wait for the Chairman — the badge in the navigation.
//
// One small module-level store: the shell polls it (only while the app is visible) and the
// Approval Center refreshes it right after a decision, so the badge never lags behind the page.

import { useEffect, useSyncExternalStore } from "react";

import { api } from "./api";

export const PENDING_POLL_MS = 20_000;

let pending = 0;
const listeners = new Set<() => void>();

function publish(value: number): void {
  if (value === pending) return;
  pending = value;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Ask the server again. A failed request keeps the last known number. */
export async function refreshPendingApprovals(): Promise<void> {
  try {
    publish((await api.pendingApprovalCount()).pending);
  } catch {
    // offline or logged out: the header's connection indicator and the session layer say so
  }
}

/** For tests: forget what an earlier test saw. */
export function resetPendingApprovals(): void {
  publish(0);
}

/** The number of pending approvals, kept fresh while the app is visible. */
export function usePendingApprovals(intervalMs = PENDING_POLL_MS): number {
  useEffect(() => {
    let timer: number | undefined;
    function stop() {
      if (timer !== undefined) window.clearInterval(timer);
      timer = undefined;
    }
    function start() {
      stop();
      void refreshPendingApprovals();
      timer = window.setInterval(() => void refreshPendingApprovals(), intervalMs);
    }
    function onVisibility() {
      if (document.visibilityState === "visible") start();
      else stop(); // hidden: no polling at all
    }
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs]);
  return useSyncExternalStore(subscribe, () => pending);
}
