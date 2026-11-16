/* AI Agent Village — service worker (hand-written, no library).

   What it does:
   - Precaches the built app shell (index.html, the content-hashed assets, icons, the offline page).
     The list is written into this file at build time by scripts/build-sw.mjs.
   - Serves those shell files from the cache.
   - Shows /offline.html when a page navigation cannot reach the village server.

   What it never does:
   - It never handles /api requests. They always go straight to the network and nothing from
     them is ever put in a cache — no data, no session, no cookies.
   - It never stores anything that was fetched with credentials: the precache requests are sent
     without cookies, and nothing is cached at run time.
*/

/* BUILD:BEGIN — replaced at build time (scripts/build-sw.mjs) */
const VERSION = "dev";
const PRECACHE = ["/offline.html"];
/* BUILD:END */

const CACHE_PREFIX = "village-shell-";
const CACHE = CACHE_PREFIX + VERSION;
const OFFLINE_URL = "/offline.html";
const SHELL = new Set(PRECACHE);
const UNREACHABLE = "Village is unreachable — check that the PC is on and Tailscale is connected.";

self.addEventListener("install", (event) => {
  // The new version waits until the page asks for it (the "Update available" toast), so an open
  // app never gets files of two versions mixed.
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { cache: "reload", credentials: "omit" })))),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith(CACHE_PREFIX) && name !== CACHE) await caches.delete(name); // old versions
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

function isApi(pathname) {
  return pathname === "/api" || pathname.startsWith("/api/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return; // writes are never touched
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApi(url.pathname)) return; // the API always goes to the network, uncached
  if (url.pathname === "/sw.js") return;

  if (request.mode === "navigate") {
    event.respondWith(openPage(request));
    return;
  }
  if (SHELL.has(url.pathname)) {
    event.respondWith(shellFile(url.pathname, request));
  }
  // anything else: the browser's normal network request, not cached
});

/** A page navigation always asks the server first. Only when the server cannot be reached
    (network error, or the Tailscale proxy answering 502/504) the offline page is shown. */
async function openPage(request) {
  try {
    const response = await fetch(request);
    if (response.status !== 502 && response.status !== 504) return response;
  } catch {
    // unreachable: fall through to the offline page
  }
  const cache = await caches.open(CACHE);
  const offline = await cache.match(OFFLINE_URL);
  return offline || new Response(UNREACHABLE, { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

/** A precached shell file: from the cache, or from the network if the cache was cleared. */
async function shellFile(pathname, request) {
  const cache = await caches.open(CACHE);
  return (await cache.match(pathname)) || fetch(request);
}
