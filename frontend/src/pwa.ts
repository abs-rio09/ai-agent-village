// Progressive Web App glue: the service worker (production builds only), the "update is
// waiting" notice and the browser's install prompt. Nothing here stores village data.

import { useSyncExternalStore } from "react";

/** Chrome's install prompt event (not in the standard DOM typings). */
export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISSED_KEY = "village.install-hint-dismissed";
const listeners = new Set<() => void>();
let installEvent: BeforeInstallPromptEvent | null = null;
let hintDismissed = readDismissed();
let waitingWorker: ServiceWorker | null = null;

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false; // storage blocked: just do not remember
  }
}

if (typeof window !== "undefined") {
  // The browser fires this only when the app can be installed and is not installed yet.
  // Its own pop-up is suppressed; the app shows one quiet hint on the login page instead.
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installEvent = event as BeforeInstallPromptEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    installEvent = null;
    emit();
  });
}

// ---------------------------------------------------------------- install hint

export interface InstallPrompt {
  /** True only while the browser offers an install and the hint was not dismissed. */
  available: boolean;
  install: () => Promise<void>;
  dismiss: () => void;
}

function dismissHint(): void {
  hintDismissed = true;
  try {
    window.localStorage.setItem(DISMISSED_KEY, "1");
  } catch {
    // not remembered across visits, still hidden for this one
  }
  emit();
}

async function install(): Promise<void> {
  const event = installEvent;
  if (!event) return;
  installEvent = null; // a prompt event can be used once
  emit();
  await event.prompt();
  const choice = await event.userChoice;
  if (choice.outcome === "dismissed") dismissHint(); // asked once, never again
}

export function useInstallPrompt(): InstallPrompt {
  const event = useSyncExternalStore(subscribe, () => installEvent);
  const dismissed = useSyncExternalStore(subscribe, () => hintDismissed);
  return { available: event !== null && !dismissed, install, dismiss: dismissHint };
}

// ---------------------------------------------------------------- updates

/** Called when a new service worker has installed and waits to take over. */
export function announceUpdate(worker: ServiceWorker | null): void {
  waitingWorker = worker;
  emit();
}

export function useUpdateWaiting(): boolean {
  return useSyncExternalStore(subscribe, () => waitingWorker) !== null;
}

/** Let the waiting version take over, then reload the page onto it. */
export function applyUpdate(): void {
  const worker = waitingWorker;
  let reloaded = false;
  const reload = () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  };
  if (!worker || !("serviceWorker" in navigator)) {
    reload();
    return;
  }
  navigator.serviceWorker.addEventListener("controllerchange", reload);
  worker.postMessage({ type: "SKIP_WAITING" });
  window.setTimeout(reload, 3000); // in case the browser never reports the change
}

async function startServiceWorker(): Promise<void> {
  try {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    const offer = (worker: ServiceWorker | null) => {
      // No controller = first install: there is nothing to update from, so no notice.
      if (worker && navigator.serviceWorker.controller) announceUpdate(worker);
    };
    offer(registration.waiting);
    registration.addEventListener("updatefound", () => {
      const worker = registration.installing;
      worker?.addEventListener("statechange", () => {
        if (worker.state === "installed") offer(worker);
      });
    });
    // An installed app can stay open for days: look for a new version when it is shown again.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") void registration.update().catch(() => undefined);
    });
  } catch {
    // No service worker (for example an unsupported browser): the app works without it.
  }
}

/** Register /sw.js. Called once from main.tsx, in production builds only. */
export function registerServiceWorker(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  if (document.readyState === "complete") void startServiceWorker();
  else window.addEventListener("load", () => void startServiceWorker(), { once: true });
}

/** Tests only: forget the install prompt, the dismissal and any waiting update. */
export function resetPwaForTests(): void {
  installEvent = null;
  waitingWorker = null;
  hintDismissed = false;
  try {
    window.localStorage.removeItem(DISMISSED_KEY);
  } catch {
    // ignore
  }
  emit();
}
