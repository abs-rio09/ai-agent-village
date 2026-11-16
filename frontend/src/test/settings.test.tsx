import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import App from "../App";
import type { DeviceSession } from "../api";
import { ALL_PAGES, isBuilt } from "../nav";
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

const THIS: DeviceSession = {
  id: 1,
  device: "Chrome on Linux",
  created_at: "2026-11-16T08:00:00Z",
  last_seen_at: "2026-11-16T09:30:00Z",
  expires_at: "2026-11-23T08:00:00Z",
  current: true,
};
const PHONE: DeviceSession = { ...THIS, id: 2, device: "Chrome on Android", current: false };
const OLD: DeviceSession = { ...THIS, id: 3, device: "Unknown device", last_seen_at: null, current: false };

function routes(sessions: DeviceSession[]): Parameters<typeof mockFetch>[0] {
  return {
    "GET /api/setup/status": { body: { setup_completed: true } },
    "GET /api/auth/me": { body: USER },
    "GET /api/village": { body: VILLAGE },
    "GET /api/health": { body: HEALTH },
    "GET /api/stats/overview": { body: STATS },
    [ACTIVITY_ROUTE]: { body: [] },
    "GET /api/auth/sessions": { body: sessions },
  };
}

describe("Devices & sessions", () => {
  it("lists the logged-in devices with created, last seen and 'This device'", async () => {
    mockFetch(routes([THIS, PHONE, OLD]));
    renderApp("/settings");

    const section = await screen.findByRole("region", { name: "Devices & sessions" });
    const items = await within(section).findAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("aria-label"))).toEqual(["Chrome on Linux", "Chrome on Android", "Unknown device"]);

    expect(within(items[0]!).getByText("This device")).toBeInTheDocument();
    expect(within(items[0]!).queryByRole("button")).not.toBeInTheDocument(); // this device is ended with Log out
    expect(items[0]).toHaveTextContent(/logged in .*2026.* · last seen .*2026/);
    expect(within(items[1]!).queryByText("This device")).not.toBeInTheDocument();
    expect(within(items[1]!).getByRole("button", { name: "Revoke Chrome on Android" })).toBeInTheDocument();
    expect(items[2]).toHaveTextContent("last seen —"); // never seen since the feature exists
    expect(within(section).getByRole("button", { name: "Log out all other devices" })).toBeEnabled();

    // the page is honest about what is not built
    expect(screen.getByRole("main")).toHaveTextContent("not built yet (coming in M8)");
    const settings = ALL_PAGES.find((page) => page.id === "settings")!;
    expect(isBuilt(settings)).toBe(true);
    expect(settings.milestone).toBe(8);
  });

  it("revokes one device", async () => {
    const table = routes([THIS, PHONE]);
    table["POST /api/auth/sessions/2/revoke"] = () => {
      table["GET /api/auth/sessions"] = { body: [THIS] };
      return { body: { revoked: 1 } };
    };
    const { callsTo } = mockFetch(table);
    const user = renderApp("/settings");

    const section = await screen.findByRole("region", { name: "Devices & sessions" });
    await user.click(await within(section).findByRole("button", { name: "Revoke Chrome on Android" }));

    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(1));
    expect(callsTo("POST /api/auth/sessions/2/revoke")).toHaveLength(1);
    expect(within(section).getByRole("status")).toHaveTextContent("Logged out Chrome on Android.");
    expect(within(section).getByRole("button", { name: "Log out all other devices" })).toBeDisabled(); // nobody else left
  });

  it("logs out all other devices", async () => {
    const table = routes([THIS, PHONE, OLD]);
    table["POST /api/auth/sessions/revoke-others"] = () => {
      table["GET /api/auth/sessions"] = { body: [THIS] };
      return { body: { revoked: 2 } };
    };
    const { callsTo } = mockFetch(table);
    const user = renderApp("/settings");

    const section = await screen.findByRole("region", { name: "Devices & sessions" });
    await within(section).findAllByRole("listitem");
    await user.click(within(section).getByRole("button", { name: "Log out all other devices" }));

    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(1));
    expect(callsTo("POST /api/auth/sessions/revoke-others")).toHaveLength(1);
    expect(within(section).getByRole("status")).toHaveTextContent("Logged out 2 other devices.");
    expect(within(section).getByText("This device")).toBeInTheDocument();
  });

  it("shows the server's message when a revoke fails and reloads the list", async () => {
    const table = routes([THIS, PHONE]);
    table["POST /api/auth/sessions/2/revoke"] = () => {
      table["GET /api/auth/sessions"] = { body: [THIS] }; // it was already gone
      return { status: 404, body: { detail: "Session not found or already logged out" } };
    };
    mockFetch(table);
    const user = renderApp("/settings");

    const section = await screen.findByRole("region", { name: "Devices & sessions" });
    await user.click(await within(section).findByRole("button", { name: "Revoke Chrome on Android" }));
    expect(await within(section).findByRole("alert")).toHaveTextContent("Session not found or already logged out");
    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(1));
  });

  it("is reachable from the sidebar without a 'coming later' badge", async () => {
    mockFetch(routes([THIS]));
    const user = renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Village pages" });
    await user.click(within(nav).getByRole("link", { name: "Application Settings" })); // exact name: no "M8" badge
    expect(await screen.findByRole("region", { name: "Devices & sessions" })).toBeInTheDocument();
  });
});
