import { act, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActivityEvent, OverviewStats } from "../api";
import Overview, { timeAgo } from "../pages/Overview";
import { ACTIVITY_ROUTE, HEALTH, VILLAGE, mockFetch } from "./helpers";

const STATS_ROUTE = "GET /api/stats/overview";
const BUSY: OverviewStats = {
  upazilas: 6, unions: 30, wards: 270, offices: 271, ward_offices: 270, agents: 7, active_agents: 5,
  running_tasks: 2, completed_tasks: 41, failed_tasks: 3, pending_approvals: 1,
};
const EMPTY: OverviewStats = {
  upazilas: 0, unions: 0, wards: 0, offices: 1, ward_offices: 0, agents: 1, active_agents: 1,
  running_tasks: 0, completed_tasks: 0, failed_tasks: 0, pending_approvals: 0,
};

function event(overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: "task:5:succeeded",
    time: new Date(Date.now() - 5 * 60_000).toISOString(),
    source: "task",
    action: "task.succeeded",
    actor: "Mina",
    agent_id: 2,
    task_id: 5,
    text: "Task #5 “help me prepare for my exam” succeeded.",
    link: "/tasks?id=5",
    tone: "good",
    ...overrides,
  };
}

function renderOverview(pollMs = 60_000) {
  render(
    <MemoryRouter>
      <Overview village={VILLAGE} pollMs={pollMs} />
    </MemoryRouter>,
  );
}

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

afterEach(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  vi.unstubAllGlobals();
});

describe("Village Overview", () => {
  it("shows every count of SPEC §13 from the backend, each linked to its page", async () => {
    mockFetch({ [STATS_ROUTE]: { body: BUSY }, [ACTIVITY_ROUTE]: { body: [] }, "GET /api/health": { body: HEALTH } });
    renderOverview();

    const expected: Array<[string, string, string, string]> = [
      ["upazilas", "Upazilas", "6", "/upazilas"],
      ["unions", "Unions", "30", "/unions"],
      ["wards", "Wards", "270", "/wards"],
      ["offices", "Offices", "271", "/wards"],
      ["agents", "Agents", "7", "/agents"],
      ["active_agents", "Active agents", "5", "/agents"],
      ["running_tasks", "Running tasks", "2", "/tasks"],
      ["pending_approvals", "Pending approvals", "1", "/approvals"],
      ["completed_tasks", "Completed tasks", "41", "/tasks"],
      ["failed_tasks", "Failed tasks", "3", "/tasks"],
    ];
    await waitFor(() => expect(screen.getByTestId("stat-upazilas")).toHaveTextContent("6"));
    for (const [key, label, value, href] of expected) {
      expect(screen.getByTestId(`stat-${key}`)).toHaveTextContent(new RegExp(`^${value}$`));
      expect(screen.getByRole("link", { name: `${label}: ${value}` })).toHaveAttribute("href", href);
    }
    expect(screen.getAllByTestId(/^stat-/)).toHaveLength(10); // exactly the ten numbers — nothing extra is invented
    expect(screen.getByText("270 ward offices + Central Administration")).toBeInTheDocument();
    expect(screen.getByText("waiting for your decision")).toBeInTheDocument();
    for (const group of ["Structure", "Agents", "Work"]) expect(screen.getByRole("region", { name: group })).toBeInTheDocument();
    expect(screen.getByTestId("overview-updated")).toHaveTextContent(/^live · updated /);
    expect(screen.queryByRole("region", { name: "Start here" })).not.toBeInTheDocument();
  });

  it("shows zeros, the start-here steps and an empty feed for an empty village", async () => {
    mockFetch({ [STATS_ROUTE]: { body: EMPTY }, [ACTIVITY_ROUTE]: { body: [] }, "GET /api/health": { body: HEALTH } });
    renderOverview();

    await waitFor(() => expect(screen.getByTestId("stat-upazilas")).toHaveTextContent("0"));
    for (const key of ["unions", "wards", "running_tasks", "pending_approvals", "completed_tasks", "failed_tasks"]) {
      expect(screen.getByTestId(`stat-${key}`)).toHaveTextContent(/^0$/);
    }
    expect(screen.getByText("nothing waits for you")).toBeInTheDocument();
    const start = screen.getByRole("region", { name: "Start here" });
    expect(start).toHaveTextContent("Your village is still empty");
    expect(within(start).getByRole("link", { name: "Create Upazilas" })).toHaveAttribute("href", "/upazilas");
    expect(within(start).getByRole("link", { name: "Add an agent" })).toHaveAttribute("href", "/agents/new");
    expect(within(start).getByRole("link", { name: "Send a request" })).toHaveAttribute("href", "/tasks");
    const feed = screen.getByRole("region", { name: "Recent activity" });
    expect(await within(feed).findByTestId("activity-empty")).toHaveTextContent("Nothing has happened yet.");
    expect(within(feed).queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("lists recent activity with actor, time and a link to the details", async () => {
    const events = [
      event({ id: "audit:9", source: "audit", action: "approval.created", actor: "Sumi", text: "'Sumi' asks for approval: Send a message to customer", link: "/approvals?id=4", tone: "warn", time: new Date(Date.now() - 20_000).toISOString() }),
      event({}),
      event({ id: "audit:3", source: "audit", action: "auth.login", actor: "Chairman (chairman)", text: "Logged in from Chrome on Linux.", link: null, tone: "muted", task_id: null, time: new Date(Date.now() - 3 * 3_600_000).toISOString() }),
    ];
    mockFetch({ [STATS_ROUTE]: { body: BUSY }, [ACTIVITY_ROUTE]: { body: events }, "GET /api/health": { body: HEALTH } });
    renderOverview();

    const feed = screen.getByRole("region", { name: "Recent activity" });
    const items = await within(feed).findAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("'Sumi' asks for approval: Send a message to customer");
    expect(items[0]).toHaveTextContent("Sumi · approval.created");
    expect(items[0]).toHaveTextContent("just now");
    expect(within(items[0]!).getByRole("link")).toHaveAttribute("href", "/approvals?id=4");
    expect(within(items[1]!).getByRole("link")).toHaveAttribute("href", "/tasks?id=5");
    expect(items[1]).toHaveTextContent("5 min ago");
    expect(items[2]).toHaveTextContent("3 h ago");
    expect(within(items[2]!).queryByRole("link")).not.toBeInTheDocument(); // no link target, no link
    expect(within(feed).queryByTestId("activity-empty")).not.toBeInTheDocument();
  });

  it("says so when the feed cannot be loaded, and keeps the numbers", async () => {
    mockFetch({ [STATS_ROUTE]: { body: BUSY }, [ACTIVITY_ROUTE]: { status: 500, body: { detail: "feed exploded" } }, "GET /api/health": { body: HEALTH } });
    renderOverview();
    const feed = screen.getByRole("region", { name: "Recent activity" });
    expect(await within(feed).findByRole("alert")).toHaveTextContent("feed exploded");
    expect(screen.getByTestId("stat-agents")).toHaveTextContent("7");
  });

  it("asks again on its own, shows the new numbers, and stops while the page is hidden", async () => {
    const routes: Parameters<typeof mockFetch>[0] = {
      [STATS_ROUTE]: { body: EMPTY },
      [ACTIVITY_ROUTE]: { body: [] },
      "GET /api/health": { body: HEALTH },
    };
    const { callsTo } = mockFetch(routes);
    renderOverview(30);

    await waitFor(() => expect(screen.getByTestId("stat-agents")).toHaveTextContent("1"));
    routes[STATS_ROUTE] = { body: { ...EMPTY, upazilas: 1, agents: 2, active_agents: 2, completed_tasks: 2 } };
    routes[ACTIVITY_ROUTE] = { body: [event({})] };
    await waitFor(() => expect(screen.getByTestId("stat-agents")).toHaveTextContent("2")); // no reload needed
    expect(screen.getByTestId("stat-completed_tasks")).toHaveTextContent("2");
    expect(await screen.findByText("Task #5 “help me prepare for my exam” succeeded.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Start here" })).not.toBeInTheDocument();

    setVisibility("hidden");
    const asked = callsTo(STATS_ROUTE).length;
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(callsTo(STATS_ROUTE)).toHaveLength(asked); // hidden: no request at all
    setVisibility("visible");
    await waitFor(() => expect(callsTo(STATS_ROUTE).length).toBeGreaterThan(asked)); // back: asks at once
    expect(callsTo(ACTIVITY_ROUTE).length).toBe(callsTo(STATS_ROUTE).length);
  });

  it("formats relative times", () => {
    const now = new Date("2026-11-16T12:00:00Z");
    expect(timeAgo("2026-11-16T11:59:40Z", now, "Asia/Dhaka")).toBe("just now");
    expect(timeAgo("2026-11-16T11:58:00Z", now, "Asia/Dhaka")).toBe("2 min ago");
    expect(timeAgo("2026-11-16T07:00:00Z", now, "Asia/Dhaka")).toBe("5 h ago");
    expect(timeAgo("2026-11-10T07:00:00Z", now, "Asia/Dhaka")).toMatch(/10/);
  });
});
