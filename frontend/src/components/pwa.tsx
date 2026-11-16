// Small PWA-related pieces of the UI: the connection indicator, the install hint and the
// "update available" toast.

import { Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { applyUpdate, useInstallPrompt, useUpdateWaiting } from "../pwa";
import { Button, cx } from "./ui";

export const HEALTH_CHECK_MS = 30_000;

type Connection = "checking" | "online" | "offline";

/**
 * Online / Offline in the header. "Online" means the village server answered /api/health;
 * the browser merely having a network is not enough. It checks at once and then every 30 s,
 * but only while the app is visible — a hidden tab or a phone in the pocket asks nothing.
 */
export function ConnectionIndicator({ intervalMs = HEALTH_CHECK_MS }: { intervalMs?: number }) {
  const [state, setState] = useState<Connection>("checking");

  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;

    async function check() {
      if (!navigator.onLine) {
        setState("offline");
        return;
      }
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (!stopped) setState(response.ok ? "online" : "offline");
      } catch {
        if (!stopped) setState("offline");
      }
    }
    function stop() {
      if (timer !== undefined) window.clearInterval(timer);
      timer = undefined;
    }
    function start() {
      stop();
      void check();
      timer = window.setInterval(() => void check(), intervalMs);
    }
    function onVisibility() {
      if (document.visibilityState === "visible") start();
      else stop(); // hidden: no polling at all
    }
    function onOnline() {
      if (document.visibilityState === "visible") start();
    }
    function onOffline() {
      setState("offline");
    }

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    onVisibility();
    return () => {
      stopped = true;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [intervalMs]);

  const label = state === "online" ? "Online" : state === "offline" ? "Offline" : "Checking";
  return (
    <span
      role="status"
      data-testid="connection"
      data-state={state}
      title={
        state === "online"
          ? "The village server is reachable."
          : state === "offline"
            ? "The village server cannot be reached. Check that the PC is on and Tailscale is connected."
            : "Checking the connection to the village server…"
      }
      className={cx(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em]",
        state === "online" && "border-paddy-500/40 bg-paddy-500/10 text-paddy-300",
        state === "offline" && "border-clay-500/40 bg-clay-500/10 text-clay-300",
        state === "checking" && "border-night-600 text-mist-400",
      )}
    >
      <span
        aria-hidden="true"
        className={cx(
          "size-1.5 rounded-full",
          state === "online" ? "bg-paddy-400" : state === "offline" ? "bg-clay-400" : "bg-mist-500",
        )}
      />
      {label}
    </span>
  );
}

/** One quiet line, only when the browser itself offers to install the app. */
export function InstallHint() {
  const { available, install, dismiss } = useInstallPrompt();
  if (!available) return null;
  return (
    <div role="note" aria-label="Install app" className="panel mt-4 flex flex-wrap items-center gap-3 p-4">
      <p className="min-w-0 flex-1 text-sm text-mist-300">Install AI Agent Village as an app on this device.</p>
      <Button size="sm" icon={<Download size={14} aria-hidden="true" />} onClick={() => void install()}>
        Install app
      </Button>
      <Button variant="ghost" size="sm" onClick={dismiss}>
        Not now
      </Button>
    </div>
  );
}

/** Shown when a new version of the app has been downloaded and waits for a reload. */
export function UpdateToast() {
  const waiting = useUpdateWaiting();
  if (!waiting) return null;
  return (
    <div
      role="status"
      aria-label="Update available"
      className="fixed inset-x-3 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-50 mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-lantern-500/50 bg-night-850 px-4 py-3 shadow-2xl md:bottom-6"
    >
      <p className="min-w-0 flex-1 text-sm text-mist-100">Update available — reload to use the new version.</p>
      <Button size="sm" icon={<RefreshCw size={14} aria-hidden="true" />} onClick={applyUpdate}>
        Reload
      </Button>
    </div>
  );
}
