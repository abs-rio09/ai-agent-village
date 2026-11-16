import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { api } from "../api";
import App from "../App";
import { ALL_PAGES, BUILT_MILESTONE, isBuilt } from "../nav";
import { SessionProvider } from "../session";
import { HEALTH, STATS, USER, VILLAGE, mockFetch, ACTIVITY_ROUTE } from "./helpers";

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

const PAGE_COUNT = 24; // the SPEC's 22 + Audit Log + Schedules

const AUTHED = {
  "GET /api/approvals/pending-count": { body: { pending: 0 } },
  "GET /api/setup/status": { body: { setup_completed: true } },
  "GET /api/auth/me": { body: USER },
  "GET /api/village": { body: VILLAGE },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats/overview": { body: STATS },
  [ACTIVITY_ROUTE]: { body: [] },
};

const UNAUTHORIZED = { status: 401, body: { detail: "Not authenticated" } };

describe("routing", () => {
  it("redirects a protected route to /login when /api/auth/me is 401", async () => {
    const { callsTo } = mockFetch({
      "GET /api/setup/status": { body: { setup_completed: true } },
      "GET /api/auth/me": UNAUTHORIZED,
    });
    renderApp("/tasks");

    expect(await screen.findByRole("heading", { name: "Welcome back, Chairman" })).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Village pages" })).not.toBeInTheDocument();
    expect(callsTo("GET /api/auth/me")).toHaveLength(1);
    expect(callsTo("GET /api/auth/me")[0]!.init?.credentials).toBe("include");
  });

  it("sends everything to the setup wizard until setup is completed", async () => {
    const { fetchMock } = mockFetch({ "GET /api/setup/status": { body: { setup_completed: false } } });
    renderApp("/login");

    expect(await screen.findByRole("heading", { name: "Found your AI Agent Village" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Village & Chairman" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // /api/auth/me is not even asked
  });

  it("keeps a finished village away from /setup", async () => {
    mockFetch(AUTHED);
    renderApp("/setup");
    expect(await screen.findByRole("heading", { level: 1, name: "Shantipur" })).toBeInTheDocument();
  });

  it("shows an error screen with retry when the server is unreachable", async () => {
    mockFetch({ "GET /api/setup/status": { status: 500, body: { detail: "boom" } } });
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("app shell", () => {
  it("shows the village name, AI badge and only backend data on the overview", async () => {
    mockFetch(AUTHED);
    renderApp("/");

    expect(await screen.findByTestId("village-name")).toHaveTextContent("Shantipur");
    expect(screen.getByTestId("ai-mode-badge")).toHaveTextContent("Demo");

    const main = screen.getByRole("main");
    expect(within(main).getByRole("heading", { level: 1, name: "Shantipur" })).toBeInTheDocument();
    expect(within(main).getAllByText("Riyan").length).toBeGreaterThan(0);
    expect(within(main).getByText("Asia/Dhaka")).toBeInTheDocument();
    expect(await within(main).findByTestId("health-status")).toHaveTextContent("ok");
    expect(within(main).getByText("9.9.9-test")).toBeInTheDocument(); // straight from /api/health
    expect(within(main).getByText("wal")).toBeInTheDocument();
  });

  it("shows a dash, not a number, when the counts cannot be loaded", async () => {
    mockFetch({ ...AUTHED, "GET /api/stats/overview": { status: 500, body: { detail: "stats exploded" } } });
    renderApp("/");
    const main = await screen.findByRole("main");
    expect(await within(main).findByText("stats exploded")).toBeInTheDocument();
    expect(within(main).getByTestId("stat-upazilas")).toHaveTextContent("—");
  });

  it.each([
    ["ollama", "Ollama: not tested"],
    ["anthropic", "Anthropic: not tested"],
  ] as const)("labels %s mode as not tested", async (mode, label) => {
    mockFetch({ ...AUTHED, "GET /api/village": { body: { ...VILLAGE, ai_mode: mode } } });
    renderApp("/");
    expect(await screen.findByTestId("ai-mode-badge")).toHaveTextContent(label);
  });

  it("no longer marks the pages built in M2, M3 and M4 as coming later", async () => {
    mockFetch(AUTHED);
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Village pages" });
    const built = [
      "Upazila Management", "Union Management", "Ward & Office Management", "Agent Management", "Agent Profile", "Task Center",
      "Approval Center", "Audit Log", "Schedules", "Memory & Knowledge Center", "Interactive Village Map",
    ];
    for (const label of built) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument(); // no "M<n>" badge in the name
    }
    expect(BUILT_MILESTONE).toBe(5);
    // not part of M3 or M4: still honest placeholders
    expect(within(nav).getByRole("link", { name: /^Agent Chat\s*M9$/ })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^AI Model Settings\s*M9$/ })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Communication History\s*M9$/ })).toBeInTheDocument();
  });

  it("lists the 22 pages from the spec plus Audit Log and Schedules in the sidebar", async () => {
    mockFetch(AUTHED);
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Village pages" });
    expect(ALL_PAGES).toHaveLength(PAGE_COUNT);
    expect(new Set(ALL_PAGES.map((page) => page.path)).size).toBe(PAGE_COUNT);
    expect(within(nav).getAllByRole("link")).toHaveLength(PAGE_COUNT);
    for (const page of ALL_PAGES) {
      expect(within(nav).getByRole("link", { name: new RegExp(`^${page.label}`) })).toBeInTheDocument();
    }
  });

  it("shows 'Coming in M<n>' with no data for pages that are not built", async () => {
    const { callsTo, fetchMock } = mockFetch(AUTHED);
    const user = renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Village pages" });

    await waitFor(() => expect(callsTo("GET /api/health")).toHaveLength(2)); // the overview and the header's connection check
    const before = fetchMock.mock.calls.length;
    await user.click(within(nav).getByRole("link", { name: /^Agent Chat/ }));
    const main = screen.getByRole("main");
    expect(within(main).getByRole("heading", { level: 1, name: "Agent Chat" })).toBeInTheDocument();
    expect(within(main).getByText("Coming in M9")).toBeInTheDocument();
    expect(within(main).queryByRole("table")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls).toHaveLength(before); // the placeholder asked the server for nothing

    for (const page of ALL_PAGES.filter((candidate) => !isBuilt(candidate))) {
      await user.click(within(nav).getByRole("link", { name: new RegExp(`^${page.label}`) }));
      expect(within(main).getByText(`Coming in M${page.milestone}`)).toBeInTheDocument();
    }
  });

  it("logs out and returns to the login page", async () => {
    const { callsTo } = mockFetch({ ...AUTHED, "POST /api/auth/logout": { body: { ok: true } } });
    const user = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("heading", { name: "Welcome back, Chairman" })).toBeInTheDocument();
    expect(callsTo("POST /api/auth/logout")).toHaveLength(1);
  });

  it("returns to /login when a later API call answers 401 (expired session)", async () => {
    let healthy = true;
    mockFetch({
      ...AUTHED,
      "GET /api/health": () => (healthy ? { body: HEALTH } : UNAUTHORIZED),
    });
    const user = renderApp("/");
    expect(await screen.findByTestId("health-status")).toHaveTextContent("ok");

    healthy = false;
    await user.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByRole("heading", { name: "Welcome back, Chairman" })).toBeInTheDocument();
  });
});

describe("api client", () => {
  it("turns FastAPI validation errors into field errors", async () => {
    mockFetch({
      "GET /api/village": {
        status: 422,
        body: { detail: [{ loc: ["body", "password"], msg: "String should have at least 10 characters", type: "string_too_short" }] },
      },
    });
    await expect(api.village()).rejects.toMatchObject({
      status: 422,
      fieldErrors: { password: "String should have at least 10 characters" },
    });
  });

  it("reports an unreachable server as status 0", async () => {
    mockFetch({});
    await expect(api.health()).rejects.toMatchObject({ status: 0 });
  });
});
