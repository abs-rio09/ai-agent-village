import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import offlinePage from "../../public/offline.html?raw";
import manifestText from "../../public/manifest.webmanifest?raw";
import swSource from "../../public/sw.js?raw";
import { isPrecachable, renderServiceWorker } from "../../scripts/build-sw.mjs";
import App from "../App";
import { ConnectionIndicator, UpdateToast } from "../components/pwa";
import { MOBILE_QUERY } from "../hooks";
import { announceUpdate, resetPwaForTests, type BeforeInstallPromptEvent } from "../pwa";
import { SessionProvider } from "../session";
import { DONE_TASK, HEALTH, STATS, USER, VILLAGE, makeTask, mockFetch } from "./helpers";

function renderApp(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const AUTHED: Parameters<typeof mockFetch>[0] = {
  "GET /api/setup/status": { body: { setup_completed: true } },
  "GET /api/auth/me": { body: USER },
  "GET /api/village": { body: VILLAGE },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats/overview": { body: STATS },
};

/** Pretend the window is `width` px wide: only media queries that match that width are true. */
function setViewport(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query);
    return {
      matches: max ? width <= Number(max[1]) : false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    };
  });
}

beforeEach(() => resetPwaForTests());

// ---------------------------------------------------------------- mobile layout

describe("mobile layout (390 px)", () => {
  it("replaces the sidebar with a bottom bar: Overview, Tasks, Agents, More", async () => {
    setViewport(390);
    mockFetch(AUTHED);
    renderApp("/");

    const bar = await screen.findByRole("navigation", { name: "Main" });
    expect(within(bar).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Overview", "Tasks", "Agents", "More"]);
    expect(within(bar).getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/");
    expect(within(bar).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(within(bar).getByRole("link", { name: "Tasks" })).toHaveAttribute("href", "/tasks");
    expect(within(bar).getByRole("link", { name: "Agents" })).toHaveAttribute("href", "/agents");
    for (const control of [...within(bar).getAllByRole("link"), within(bar).getByRole("button", { name: "More" })]) {
      expect(control.className).toContain("min-h-14"); // 56 px: above the 44 px touch minimum
    }
    expect(bar.className).toContain("safe-area-inset-bottom");

    // no sidebar and no hamburger on a phone
    expect(screen.queryByRole("navigation", { name: "Village pages" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open menu" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(MOBILE_QUERY).toBe("(max-width: 768px)");
  });

  it("opens the full menu as a sheet from More and closes it on navigation", async () => {
    setViewport(390);
    mockFetch(AUTHED);
    const user = renderApp("/");

    const more = await screen.findByRole("button", { name: "More" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(more);

    const sheet = screen.getByRole("dialog", { name: "All pages" });
    expect(more).toHaveAttribute("aria-expanded", "true");
    const links = within(within(sheet).getByRole("navigation", { name: "Village pages" })).getAllByRole("link");
    expect(links).toHaveLength(23); // every page of the village (the SPEC's 22 + Audit Log)
    for (const link of links) expect(link.className).toContain("min-h-11"); // 44 px touch targets
    expect(within(sheet).getByText("chairman")).toBeInTheDocument();
    expect(within(sheet).getByTestId("ai-mode-badge")).toHaveTextContent("Demo");

    await user.click(within(sheet).getByRole("link", { name: /^Approval Center/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("heading", { name: "Approval Center" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(within(screen.getByRole("dialog", { name: "All pages" })).getByRole("button", { name: "Close menu" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the desktop layout unchanged above 768 px", async () => {
    setViewport(1280);
    mockFetch(AUTHED);
    renderApp("/");
    expect(await screen.findByRole("navigation", { name: "Village pages" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-mode-badge")).toBeInTheDocument();
  });

  it("uses the bottom bar at exactly 768 px and the desktop layout at 769 px", async () => {
    setViewport(768);
    mockFetch(AUTHED);
    const first = render(
      <MemoryRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
    first.unmount();

    setViewport(769);
    renderApp("/");
    expect(await screen.findByRole("navigation", { name: "Village pages" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("shows an opened task full-screen with a Back button on a phone", async () => {
    setViewport(390);
    mockFetch({ ...AUTHED, "GET /api/tasks?top_level=true": { body: [DONE_TASK] }, "GET /api/tasks/1": { body: DONE_TASK } });
    const user = renderApp("/tasks");

    // the list view: send form first, then the requests
    const form = await screen.findByRole("form", { name: "Send to Central Manager" });
    const list = screen.getByRole("region", { name: "Tasks" });
    expect(form.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const row = await within(list).findByRole("link", { name: /#1 help me prepare/ });
    expect(row.className).toContain("min-h-11");

    await user.click(row);
    expect(await screen.findByRole("region", { name: "Task 1" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Send to Central Manager" })).not.toBeInTheDocument(); // only the task
    expect(screen.queryByRole("region", { name: "Tasks" })).not.toBeInTheDocument();

    const back = screen.getByRole("link", { name: "Back to requests" });
    expect(back.className).toContain("min-h-11");
    await user.click(back);
    expect(await screen.findByRole("form", { name: "Send to Central Manager" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Task 1" })).not.toBeInTheDocument();
  });

  it("shows the task below the list on a desktop, as before", async () => {
    setViewport(1280);
    mockFetch({ ...AUTHED, "GET /api/tasks?top_level=true": { body: [makeTask()] }, "GET /api/tasks/1": { body: { ...makeTask(), children: [], messages: [] } } });
    renderApp("/tasks?id=1");
    expect(await screen.findByRole("region", { name: "Task 1" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Send to Central Manager" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Back to requests" })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- connection indicator

describe("connection indicator", () => {
  let visibility: DocumentVisibilityState = "visible";

  beforeEach(() => {
    visibility = "visible";
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
  });
  afterEach(() => {
    delete (document as { visibilityState?: unknown }).visibilityState;
  });

  function show(next: DocumentVisibilityState) {
    visibility = next;
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
  }
  const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  it("says Online when the village server answers /api/health", async () => {
    const { callsTo } = mockFetch({ "GET /api/health": { body: HEALTH } });
    render(<ConnectionIndicator />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("Checking");
    await waitFor(() => expect(badge).toHaveTextContent("Online"));
    expect(badge).toHaveAttribute("data-state", "online");
    expect(callsTo("GET /api/health")).toHaveLength(1);
    expect(callsTo("GET /api/health")[0]!.init?.cache).toBe("no-store");
  });

  it("says Offline when the server cannot be reached or answers an error", async () => {
    mockFetch({}); // every request fails, as it does when the PC is off
    const first = render(<ConnectionIndicator />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Offline"));
    expect(screen.getByRole("status").title).toContain("Check that the PC is on and Tailscale is connected");
    first.unmount();

    mockFetch({ "GET /api/health": { status: 502, body: {} } }); // the proxy is up, the village is not
    render(<ConnectionIndicator />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Offline"));
  });

  it("says Offline without asking when the browser has no network, and checks again when it returns", async () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const { callsTo } = mockFetch({ "GET /api/health": { body: HEALTH } });
    render(<ConnectionIndicator />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Offline"));
    expect(callsTo("GET /api/health")).toHaveLength(0);

    onLine.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Online"));
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByRole("status")).toHaveTextContent("Offline");
  });

  it("checks on a timer only while the app is visible and stops when it is hidden", async () => {
    const { callsTo } = mockFetch({ "GET /api/health": { body: HEALTH } });
    render(<ConnectionIndicator intervalMs={20} />);
    await waitFor(() => expect(callsTo("GET /api/health").length).toBeGreaterThanOrEqual(3)); // it keeps checking

    show("hidden");
    await pause(30); // let a request that was already on its way finish
    const whileHidden = callsTo("GET /api/health").length;
    await pause(200);
    expect(callsTo("GET /api/health")).toHaveLength(whileHidden); // not one request while hidden

    show("visible");
    await waitFor(() => expect(callsTo("GET /api/health").length).toBeGreaterThan(whileHidden + 1)); // at once, then on the timer
  });

  it("does not start checking when the app starts hidden, and stops on unmount", async () => {
    visibility = "hidden";
    const { callsTo } = mockFetch({ "GET /api/health": { body: HEALTH } });
    const view = render(<ConnectionIndicator intervalMs={20} />);
    await pause(120);
    expect(callsTo("GET /api/health")).toHaveLength(0);
    show("visible");
    await waitFor(() => expect(callsTo("GET /api/health").length).toBeGreaterThanOrEqual(1));
    view.unmount();
    await pause(30);
    const afterUnmount = callsTo("GET /api/health").length;
    await pause(120);
    expect(callsTo("GET /api/health")).toHaveLength(afterUnmount);
  });

  it("is shown in the header of the app", async () => {
    mockFetch(AUTHED);
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("connection")).toHaveTextContent("Online"));
    expect(screen.getByRole("banner")).toContainElement(screen.getByTestId("connection"));
  });
});

// ---------------------------------------------------------------- install hint + update toast

function offerInstall(outcome: "accepted" | "dismissed" = "accepted") {
  const event = new Event("beforeinstallprompt", { cancelable: true }) as BeforeInstallPromptEvent;
  event.prompt = vi.fn(async () => undefined);
  event.userChoice = Promise.resolve({ outcome });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

const ANONYMOUS: Parameters<typeof mockFetch>[0] = {
  "GET /api/setup/status": { body: { setup_completed: true } },
  "GET /api/auth/me": { status: 401, body: { detail: "Not authenticated" } },
};

describe("install hint", () => {
  it("is hidden when the browser does not offer an install", async () => {
    mockFetch(ANONYMOUS);
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Welcome back, Chairman" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
    expect(screen.queryByRole("note", { name: "Install app" })).not.toBeInTheDocument();
    expect(screen.getByText("Local only · 127.0.0.1")).toBeInTheDocument();
  });

  it("appears on the login page when the browser offers it, and installs on request", async () => {
    mockFetch(ANONYMOUS);
    const user = renderApp("/login");
    await screen.findByRole("heading", { name: "Welcome back, Chairman" });

    const event = offerInstall("accepted");
    expect(event.defaultPrevented).toBe(true); // the browser's own pop-up is suppressed
    expect(event.prompt).not.toHaveBeenCalled(); // nothing happens until the Chairman asks
    await user.click(screen.getByRole("button", { name: "Install app" }));
    expect(event.prompt).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument());
  });

  it("never comes back after 'Not now' or after the browser's prompt was dismissed", async () => {
    mockFetch(ANONYMOUS);
    const user = renderApp("/login");
    await screen.findByRole("heading", { name: "Welcome back, Chairman" });

    offerInstall();
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
    offerInstall(); // the browser offers again on a later visit
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("village.install-hint-dismissed")).toBe("1");

    act(() => resetPwaForTests());
    offerInstall("dismissed");
    await user.click(screen.getByRole("button", { name: "Install app" }));
    await waitFor(() => expect(window.localStorage.getItem("village.install-hint-dismissed")).toBe("1"));
    offerInstall();
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
  });

  it("disappears once the app is installed", async () => {
    mockFetch(ANONYMOUS);
    renderApp("/login");
    await screen.findByRole("heading", { name: "Welcome back, Chairman" });
    offerInstall();
    expect(screen.getByRole("button", { name: "Install app" })).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event("appinstalled"));
    });
    expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
  });
});

describe("update toast", () => {
  it("shows 'Update available' only when a new version is waiting, and tells it to take over", async () => {
    const user = userEvent.setup();
    render(<UpdateToast />);
    expect(screen.queryByRole("status", { name: "Update available" })).not.toBeInTheDocument();

    const worker = { postMessage: vi.fn() } as unknown as ServiceWorker;
    const container = { addEventListener: vi.fn() };
    vi.stubGlobal("navigator", Object.assign(Object.create(navigator), { serviceWorker: container }));
    act(() => announceUpdate(worker));
    const toast = screen.getByRole("status", { name: "Update available" });
    expect(toast).toHaveTextContent("Update available — reload to use the new version.");

    await user.click(within(toast).getByRole("button", { name: "Reload" }));
    expect(worker.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    expect(container.addEventListener).toHaveBeenCalledWith("controllerchange", expect.any(Function));
  });
});

// ---------------------------------------------------------------- manifest + offline page

describe("manifest and offline page", () => {
  it("has what an installable app needs", () => {
    const manifest = JSON.parse(manifestText) as Record<string, unknown> & { icons: Array<Record<string, string>> };
    expect(manifest).toMatchObject({ name: "AI Agent Village", short_name: "Village", start_url: "/", scope: "/", display: "standalone" });
    expect(manifest.theme_color).toBe("#060b0a");
    expect(manifest.background_color).toBe("#060b0a");
    expect(manifest.icons.map((icon) => [icon.sizes, icon.purpose, icon.type])).toEqual([
      ["192x192", "any", "image/png"],
      ["512x512", "any", "image/png"],
      ["512x512", "maskable", "image/png"],
    ]);
  });

  it("offline page says the village is unreachable and shows no data and no script", () => {
    expect(offlinePage).toContain("Village is unreachable");
    expect(offlinePage).toContain("Check that the PC is on and Tailscale is connected.");
    expect(offlinePage).not.toMatch(/<script/i); // the page's CSP forbids inline scripts anyway
    expect(offlinePage).not.toContain("/api/");
    expect(offlinePage).toContain('href="/"'); // "Try again"
  });
});

// ---------------------------------------------------------------- service worker

interface FakeEvent {
  request: { method: string; url: string; mode: string };
  respondWith: ReturnType<typeof vi.fn>;
}

/** Run a service worker source against fake `self`, `caches` and `fetch`. */
function loadWorker(source: string) {
  const handlers: Record<string, (event: never) => void> = {};
  const stores = new Map<string, Map<string, Response>>();
  const writes: string[] = [];
  const precacheRequests: Array<{ url: string; init: RequestInit }> = [];
  class FakeRequest {
    constructor(
      readonly url: string,
      readonly init: RequestInit = {},
    ) {}
  }
  const cacheOf = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name)!;
    return {
      addAll: async (requests: FakeRequest[]) => {
        for (const request of requests) {
          precacheRequests.push({ url: request.url, init: request.init });
          store.set(request.url, new Response(`precached ${request.url}`));
        }
      },
      // like the real Cache API: every match hands out a fresh Response
      match: async (key: string | { url: string }) => store.get(typeof key === "string" ? key : new URL(key.url).pathname)?.clone(),
      put: async (key: string) => {
        writes.push(key);
      },
      add: async (key: string) => {
        writes.push(key);
      },
    };
  };
  const caches = {
    open: async (name: string) => cacheOf(name),
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async () => undefined,
  };
  const self = {
    location: { origin: "https://village.test" },
    addEventListener: (type: string, handler: (event: never) => void) => {
      handlers[type] = handler;
    },
    clients: { claim: vi.fn(async () => undefined) },
    skipWaiting: vi.fn(),
  };
  const fetchMock = vi.fn<(request: unknown) => Promise<Response>>();
  new Function("self", "caches", "fetch", "Request", source)(self, caches, fetchMock, FakeRequest);

  async function lifecycle(type: "install" | "activate") {
    let work: Promise<unknown> = Promise.resolve();
    handlers[type]!({ waitUntil: (promise: Promise<unknown>) => (work = promise) } as never);
    await work;
  }
  function request(url: string, init: { method?: string; mode?: string } = {}): FakeEvent {
    const event: FakeEvent = {
      request: { method: init.method ?? "GET", url: `https://village.test${url}`, mode: init.mode ?? "cors" },
      respondWith: vi.fn(),
    };
    handlers.fetch!(event as never);
    return event;
  }
  const answer = async (event: FakeEvent) => (await event.respondWith.mock.calls[0]![0]) as Response;
  return { self, stores, writes, precacheRequests, fetchMock, handlers, lifecycle, request, answer };
}

const BUILT = renderServiceWorker(swSource, "v2", ["/assets/index-abc.js", "/assets/index-abc.css", "/index.html", "/offline.html"]);

describe("service worker (public/sw.js)", () => {
  it("never puts anything into a cache at run time: the only cache write is the precache", () => {
    expect(swSource).not.toMatch(/\.put\(/);
    expect(swSource).not.toMatch(/\.add\(/);
    expect(swSource.match(/addAll\(/g)).toHaveLength(1);
    expect(swSource).toContain('credentials: "omit"'); // the precache is fetched without cookies
    expect(swSource).toMatch(/if \(isApi\(url\.pathname\)\) return;/);
    // the API check comes before anything can answer a request
    expect(swSource.indexOf("if (isApi(url.pathname)) return;")).toBeLessThan(swSource.indexOf("event.respondWith("));
  });

  it("precaches the shell without credentials and removes the caches of older versions", async () => {
    const worker = loadWorker(BUILT);
    worker.stores.set("village-shell-v1", new Map([["/index.html", new Response("old")]]));
    worker.stores.set("some-other-cache", new Map());

    await worker.lifecycle("install");
    expect(worker.precacheRequests.map((item) => item.url)).toEqual(["/assets/index-abc.js", "/assets/index-abc.css", "/index.html", "/offline.html"]);
    expect(worker.precacheRequests.every((item) => item.init.credentials === "omit" && item.init.cache === "reload")).toBe(true);
    expect(worker.self.skipWaiting).not.toHaveBeenCalled(); // it waits for the "Update available" toast
    expect([...worker.stores.keys()].sort()).toEqual(["some-other-cache", "village-shell-v1", "village-shell-v2"]);

    await worker.lifecycle("activate");
    expect([...worker.stores.keys()].sort()).toEqual(["some-other-cache", "village-shell-v2"]); // v1 is gone
    expect(worker.self.clients.claim).toHaveBeenCalled();

    worker.handlers.message!({ data: { type: "SKIP_WAITING" } } as never);
    expect(worker.self.skipWaiting).toHaveBeenCalledTimes(1);
    worker.handlers.message!({ data: { type: "something else" } } as never);
    expect(worker.self.skipWaiting).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["GET", "/api/health", "cors"],
    ["GET", "/api/auth/me", "cors"],
    ["GET", "/api/tasks?top_level=true", "cors"],
    ["GET", "/api", "navigate"],
    ["GET", "/api/tasks/1", "navigate"],
    ["POST", "/api/auth/login", "cors"],
    ["POST", "/api/tasks", "cors"],
    ["DELETE", "/api/agents/2", "cors"],
  ])("leaves %s %s to the network and caches nothing", async (method, url, mode) => {
    const worker = loadWorker(BUILT);
    await worker.lifecycle("install");
    const before = [...worker.stores.get("village-shell-v2")!.keys()];

    const event = worker.request(url, { method, mode });
    expect(event.respondWith).not.toHaveBeenCalled(); // not handled at all: the browser goes to the network
    expect(worker.fetchMock).not.toHaveBeenCalled();
    expect(worker.writes).toEqual([]);
    expect([...worker.stores.get("village-shell-v2")!.keys()]).toEqual(before);
  });

  it("does not handle other origins, its own file, or files that are not part of the shell", async () => {
    const worker = loadWorker(BUILT);
    await worker.lifecycle("install");
    const foreign: FakeEvent = { request: { method: "GET", url: "https://elsewhere.test/index.html", mode: "cors" }, respondWith: vi.fn() };
    worker.handlers.fetch!(foreign as never);
    expect(foreign.respondWith).not.toHaveBeenCalled();
    expect(worker.request("/sw.js").respondWith).not.toHaveBeenCalled();
    expect(worker.request("/not-in-the-shell.png").respondWith).not.toHaveBeenCalled();
    expect(worker.fetchMock).not.toHaveBeenCalled();
  });

  it("serves shell files from the cache", async () => {
    const worker = loadWorker(BUILT);
    await worker.lifecycle("install");
    const event = worker.request("/assets/index-abc.js");
    expect(await (await worker.answer(event)).text()).toBe("precached /assets/index-abc.js");
    expect(worker.fetchMock).not.toHaveBeenCalled();
  });

  it("opens pages from the server and stores nothing", async () => {
    const worker = loadWorker(BUILT);
    await worker.lifecycle("install");
    worker.fetchMock.mockResolvedValue(new Response("fresh page from the server"));
    const event = worker.request("/tasks", { mode: "navigate" });
    expect(await (await worker.answer(event)).text()).toBe("fresh page from the server");
    expect(worker.fetchMock).toHaveBeenCalledTimes(1);
    expect(worker.writes).toEqual([]);
  });

  it("shows the offline page when the server cannot be reached", async () => {
    const worker = loadWorker(BUILT);
    await worker.lifecycle("install");

    worker.fetchMock.mockRejectedValue(new TypeError("Failed to fetch")); // PC off, or Tailscale disconnected
    expect(await (await worker.answer(worker.request("/", { mode: "navigate" }))).text()).toBe("precached /offline.html");

    worker.fetchMock.mockResolvedValue(new Response("bad gateway", { status: 502 })); // the proxy answers, the village does not
    expect(await (await worker.answer(worker.request("/agents", { mode: "navigate" }))).text()).toBe("precached /offline.html");

    worker.fetchMock.mockResolvedValue(new Response("not found", { status: 404 })); // a real answer is passed on
    expect((await worker.answer(worker.request("/nope", { mode: "navigate" }))).status).toBe(404);
  });

  it("still says the village is unreachable when even the offline page is missing", async () => {
    const worker = loadWorker(BUILT); // not installed: the cache is empty
    worker.fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const response = await worker.answer(worker.request("/", { mode: "navigate" }));
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("Village is unreachable — check that the PC is on and Tailscale is connected.");
  });

  it("works as committed too (the unbuilt file precaches only the offline page)", async () => {
    const worker = loadWorker(swSource);
    await worker.lifecycle("install");
    expect(worker.precacheRequests.map((item) => item.url)).toEqual(["/offline.html"]);
    expect([...worker.stores.keys()]).toEqual(["village-shell-dev"]);
  });
});

describe("service worker build step (scripts/build-sw.mjs)", () => {
  it("writes the version and the precache list into the build block only", () => {
    expect(BUILT).toContain('const VERSION = "v2";');
    expect(BUILT).toContain('"/assets/index-abc.js"');
    expect(BUILT).not.toContain('const VERSION = "dev";');
    expect(BUILT.replace(/\/\* BUILD:BEGIN[\s\S]*?\/\* BUILD:END \*\//, "")).toBe(swSource.replace(/\/\* BUILD:BEGIN[\s\S]*?\/\* BUILD:END \*\//, ""));
    expect(() => renderServiceWorker("no markers here", "v1", [])).toThrow(/BUILD:BEGIN/);
  });

  it("never lists the worker itself, source maps or anything under /api", () => {
    expect(["/index.html", "/assets/a.js", "/icons/icon-192.png", "/offline.html"].every(isPrecachable)).toBe(true);
    expect(["/sw.js", "/assets/a.js.map", "/api", "/api/health"].some(isPrecachable)).toBe(false);
  });
});
