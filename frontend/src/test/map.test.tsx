import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MapAgent, MapBuilding, MapView } from "../api";
import { fitText, gridColumns, gridLayout, ringLayout, type Point } from "../components/map/layout";
import VillageMap from "../pages/VillageMap";
import { mockFetch } from "./helpers";

type Routes = Parameters<typeof mockFetch>[0];

const MANAGER: MapAgent = { id: 1, name: "Central Manager", role: "Village Manager", template_key: "village_manager", activity: "working", current_task_id: 9 };
const MINA: MapAgent = { id: 2, name: "Mina", role: "Study Assistant", template_key: "study_assistant", activity: "idle", current_task_id: null };
const SUMI: MapAgent = { id: 3, name: "Sumi", role: "Customer Support Agent", template_key: "customer_support", activity: "waiting", current_task_id: 10 };

function building(overrides: Partial<MapBuilding>): MapBuilding {
  return { id: 1, type: "upazila", name: "Study Upazila", detail: "", child_count: 5, child_label: "Unions", agent_count: 0, active_tasks: 0, agents: [], target: { level: "upazila", id: 1 }, ...overrides };
}

const CENTRAL = building({ id: 100, type: "central", name: "Central Administration", detail: "The village's own office", child_count: 1, child_label: "Agents", agent_count: 1, active_tasks: 1, agents: [MANAGER], target: null });
const STUDY = building({ id: 1, agent_count: 1, agents: [MINA] });
const BUSINESS = building({ id: 2, name: "Business Upazila", child_count: 1, agent_count: 1, active_tasks: 2, agents: [SUMI], target: { level: "upazila", id: 2 } });

const VILLAGE: MapView = {
  level: "village", id: null, name: "Shantipur",
  breadcrumb: [{ level: "village", id: null, label: "Shantipur" }],
  parent: null, buildings: [CENTRAL, STUDY, BUSINESS], office_name: null, agents: [], agent_count: 3, active_tasks: 3,
};
const UPAZILA: MapView = {
  level: "upazila", id: 1, name: "Study Upazila",
  breadcrumb: [{ level: "village", id: null, label: "Shantipur" }, { level: "upazila", id: 1, label: "Study Upazila" }],
  parent: { level: "village", id: null },
  buildings: ["Academic Management", "Course Learning", "Exam Preparation", "Research Paper Learning", "Academic Documentation"].map((name, index) =>
    building({ id: 11 + index, type: "union", name, child_count: 9, child_label: "Wards", agent_count: index === 0 ? 1 : 0, agents: index === 0 ? [MINA] : [], target: { level: "union", id: 11 + index } }),
  ),
  office_name: null, agents: [], agent_count: 1, active_tasks: 0,
};
const UNION: MapView = {
  level: "union", id: 11, name: "Academic Management",
  breadcrumb: [...UPAZILA.breadcrumb, { level: "union", id: 11, label: "Academic Management" }],
  parent: { level: "upazila", id: 1 },
  buildings: Array.from({ length: 9 }, (_, index) =>
    building({ id: 111 + index, type: "ward", name: `Ward ${index + 1}: Ward name ${index + 1}`, detail: `Office ${index + 1}`, child_count: index === 0 ? 1 : 0, child_label: "Agents", agent_count: index === 0 ? 1 : 0, agents: index === 0 ? [MINA] : [], target: { level: "ward", id: 111 + index } }),
  ),
  office_name: null, agents: [], agent_count: 1, active_tasks: 0,
};
const WARD: MapView = {
  level: "ward", id: 111, name: "Ward 1: Ward name 1",
  breadcrumb: [...UNION.breadcrumb, { level: "ward", id: 111, label: "Ward 1: Ward name 1" }],
  parent: { level: "union", id: 11 }, buildings: [], office_name: "Class Routine Office", agents: [MINA], agent_count: 1, active_tasks: 0,
};

const ROUTES: Routes = {
  "GET /api/map?level=village": { body: VILLAGE },
  "GET /api/map?level=upazila&id=1": { body: UPAZILA },
  "GET /api/map?level=union&id=11": { body: UNION },
  "GET /api/map?level=ward&id=111": { body: WARD },
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderMap(path = "/map", pollMs = 60_000) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes>
        <Route path="/map" element={<VillageMap pollMs={pollMs} />} />
        <Route path="/agents/profile" element={<p>agent profile</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

function setViewport(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query);
    return { matches: max ? width <= Number(max[1]) : false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined };
  });
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

function apart(points: Point[]): number {
  let closest = Infinity;
  points.forEach((a, i) => points.slice(i + 1).forEach((b) => (closest = Math.min(closest, Math.hypot(a.x - b.x, a.y - b.y)))));
  return closest;
}

describe("map layout (computed from counts)", () => {
  it.each([false, true])("places 0 to 12 buildings around the plaza without overlap (portrait: %s)", (portrait) => {
    for (let count = 0; count <= 12; count += 1) {
      const layout = ringLayout(count, portrait);
      expect(layout.slots).toHaveLength(count);
      for (const slot of layout.slots) {
        expect(slot.x).toBeGreaterThan(40);
        expect(slot.x).toBeLessThan(layout.width - 40);
        expect(slot.y).toBeGreaterThan(70); // room for the roof
        expect(slot.y).toBeLessThan(layout.height - 60); // room for the sign and the robots
        expect(Math.hypot(slot.x - layout.centre.x, slot.y - layout.centre.y)).toBeGreaterThan(portrait ? 70 : 110); // not on the plaza
      }
      if (count > 1) expect(apart(layout.slots)).toBeGreaterThan(portrait ? 84 : 120);
      expect(layout.gardens.length).toBeGreaterThan(0);
    }
    expect(ringLayout(6, portrait).slots[0]).toEqual({ x: ringLayout(6, portrait).centre.x, y: expect.any(Number) }); // the first one is at the top
  });

  it("is the same for the same count: no position depends on a name", () => {
    expect(ringLayout(6, false)).toEqual(ringLayout(6, false));
    expect(gridLayout(9, true)).toEqual(gridLayout(9, true));
  });

  it.each([false, true])("puts 0 to 20 items in tidy rows inside the map (portrait: %s)", (portrait) => {
    for (const count of [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 20]) {
      const layout = gridLayout(count, portrait);
      expect(layout.slots).toHaveLength(count);
      expect(layout.rows).toBe(Math.max(1, Math.ceil(count / layout.columns)));
      for (const slot of layout.slots) {
        expect(slot.x).toBeGreaterThanOrEqual(layout.cell.width / 2);
        expect(slot.x).toBeLessThanOrEqual(layout.width - layout.cell.width / 2);
        expect(slot.y).toBeLessThan(layout.height);
      }
      if (count > 1) expect(apart(layout.slots)).toBeGreaterThan(100);
    }
    expect(gridColumns(9, false)).toBe(3); // nine Wards: a 3 × 3 block
    expect(gridColumns(9, true)).toBe(2);
    expect(gridColumns(1, true)).toBe(1);
    expect(gridLayout(5, false).slots.slice(3).map((slot) => slot.y)).toEqual([gridLayout(5, false).slots[3]!.y, gridLayout(5, false).slots[3]!.y]);
  });

  it("shortens long names for a sign", () => {
    expect(fitText("Study Upazila", 20)).toBe("Study Upazila");
    expect(fitText("Career & Job Preparation Upazila", 16)).toBe("Career & Job Pr…");
  });
});

describe("Interactive Village Map", () => {
  it("draws the village level: Central Administration, one building per Upazila, robots and task counts", async () => {
    mockFetch(ROUTES);
    renderMap();

    const scene = await screen.findByTestId("map-scene");
    expect(scene).toHaveAttribute("data-level", "village");
    expect(scene).toHaveAccessibleName("Map of Shantipur");
    expect(within(scene).getByRole("img", { name: "Central Administration: 1 Agent, 1 active task" })).toBeInTheDocument();
    expect(within(scene).getByRole("link", { name: "Study Upazila: 5 Unions, 1 agent, 0 active tasks — open" })).toBeInTheDocument();
    expect(within(scene).getByRole("link", { name: "Business Upazila: 1 Union, 1 agent, 2 active tasks — open" })).toBeInTheDocument();
    // active-task counts are on the buildings that have some
    expect(within(scene).getByTestId("map-tasks-upazila-2")).toHaveTextContent("2");
    expect(within(scene).getByTestId("map-tasks-central-100")).toHaveTextContent("1");
    expect(within(scene).queryByTestId("map-tasks-upazila-1")).not.toBeInTheDocument();
    // the agents stand at their workplace, with their activity
    expect(within(scene).getByRole("link", { name: "Central Manager, Village Manager, working on task #9 — open profile" })).toBeInTheDocument();
    expect(within(scene).getByRole("link", { name: "Sumi, Customer Support Agent, waiting for your approval (task #10) — open profile" })).toBeInTheDocument();
    expect(within(scene).getByRole("link", { name: "Mina, Study Assistant, idle — open profile" })).toBeInTheDocument();
    expect(scene.querySelector("image, img")).toBeNull(); // SVG shapes only
    expect(screen.getByTestId("map-summary")).toHaveTextContent("Village · 3 agents · 3 active tasks");
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled(); // nothing above the village
  });

  it("goes Village → Upazila → Union → Ward by click, and an agent opens its profile", async () => {
    const { callsTo } = mockFetch(ROUTES);
    const user = renderMap();

    await user.click(await screen.findByRole("link", { name: /^Study Upazila: .* — open$/ }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "upazila"));
    expect(screen.getByTestId("where")).toHaveTextContent("/map?level=upazila&id=1");
    expect(callsTo("GET /api/map?level=upazila&id=1")).toHaveLength(1);
    expect(screen.getAllByRole("link", { name: /: 9 Wards, .* — open$/ })).toHaveLength(5);

    await user.click(screen.getByRole("link", { name: /^Academic Management: / }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "union"));
    expect(screen.getAllByTestId(/^map-building-ward-/)).toHaveLength(9);

    await user.click(screen.getByRole("link", { name: /^Ward 1: Ward name 1: 1 Agent, / }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "ward"));
    expect(screen.getByTestId("where")).toHaveTextContent("/map?level=ward&id=111");
    const scene = screen.getByTestId("map-scene");
    expect(scene).toHaveTextContent("Class Routine Office");
    expect(within(scene).getByTestId("map-workspace-2")).toHaveTextContent("Mina");
    expect(screen.getByTestId("map-summary")).toHaveTextContent("Ward · 1 agent · 0 active tasks");

    await user.click(within(scene).getByRole("link", { name: "Mina, Study Assistant, idle — open profile" }));
    expect(await screen.findByText("agent profile")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/agents/profile?id=2");
  });

  it("goes back up with the breadcrumb and with Back", async () => {
    mockFetch(ROUTES);
    const user = renderMap("/map?level=ward&id=111");

    const crumbs = await screen.findByRole("navigation", { name: "Where you are" });
    expect(within(crumbs).getAllByRole("listitem").map((item) => item.textContent?.replace("›", ""))).toEqual([
      "Shantipur", "Study Upazila", "Academic Management", "Ward 1: Ward name 1",
    ]);
    expect(within(crumbs).getByText("Ward 1: Ward name 1")).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "Back" })); // one level up
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "union"));
    expect(screen.getByTestId("where")).toHaveTextContent("/map?level=union&id=11");

    await user.click(within(screen.getByRole("navigation", { name: "Where you are" })).getByRole("button", { name: "Study Upazila" }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "upazila"));

    await user.click(within(screen.getByRole("navigation", { name: "Where you are" })).getByRole("button", { name: "Shantipur" }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "village"));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/map$/);
  });

  it("works from the keyboard: a building is focusable and opens with Enter", async () => {
    mockFetch(ROUTES);
    const user = renderMap();
    const study = await screen.findByRole("link", { name: /^Study Upazila: / });
    expect(study).toHaveAttribute("tabindex", "0");
    study.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "upazila"));
    const union = screen.getByRole("link", { name: /^Course Learning: / });
    union.focus();
    await user.keyboard(" ");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/map?level=union&id=12"));
  });

  it("offers the same places and agents as a list, with the same address", async () => {
    mockFetch(ROUTES);
    const user = renderMap();
    await screen.findByTestId("map-scene");
    expect(screen.getByRole("button", { name: "Map view" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "List view" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/map?view=list");
    expect(screen.queryByTestId("map-scene")).not.toBeInTheDocument();
    const list = screen.getByTestId("map-list");
    // the same three buildings, the same numbers, the same agents
    expect(within(list).getByTestId("list-item-central-100")).toHaveTextContent("Central Administration");
    expect(within(list).getByTestId("list-item-central-100")).toHaveTextContent("1 Agent · 1 active task");
    expect(within(list).getByTestId("list-item-upazila-2")).toHaveTextContent("1 Union · 1 agent · 2 active tasks");
    expect(within(list).getByRole("link", { name: "Sumi, Customer Support Agent, waiting for your approval (task #10) — open profile" })).toHaveAttribute("href", "/agents/profile?id=3");
    expect(within(list).getByRole("link", { name: /^Central Manager, / })).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: /^Central Administration/ })).not.toBeInTheDocument(); // nothing below it

    // drilling down in the list keeps the list, and the address is the map's address
    await user.click(within(list).getByRole("button", { name: /^Study Upazila: .* — open$/ }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/map?level=upazila&id=1&view=list"));
    await waitFor(() => expect(within(screen.getByTestId("map-list")).getAllByRole("button")).toHaveLength(5));
    await user.click(within(screen.getByTestId("map-list")).getByRole("button", { name: /^Academic Management: / }));
    await waitFor(() => expect(within(screen.getByTestId("map-list")).getAllByRole("button")).toHaveLength(9));
    await user.click(within(screen.getByTestId("map-list")).getByRole("button", { name: /^Ward 1: Ward name 1: / }));
    const office = await screen.findByRole("list", { name: "Agents of this Office" });
    expect(within(office).getByRole("link", { name: "Mina, Study Assistant, idle — open profile" })).toHaveAttribute("href", "/agents/profile?id=2");
    expect(screen.getByTestId("map-list")).toHaveTextContent("Class Routine Office");

    // switching back shows the map of the very same place
    await user.click(screen.getByRole("button", { name: "Map view" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/map?level=ward&id=111");
    expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "ward");
  });

  it("shows an empty village honestly: only Central Administration and a hint", async () => {
    const empty: MapView = { ...VILLAGE, buildings: [{ ...CENTRAL, active_tasks: 0, agents: [{ ...MANAGER, activity: "idle", current_task_id: null }] }], agent_count: 1, active_tasks: 0 };
    mockFetch({ "GET /api/map?level=village": { body: empty } });
    renderMap();
    const scene = await screen.findByTestId("map-scene");
    expect(within(scene).getAllByTestId(/^map-building-/)).toHaveLength(1);
    expect(within(scene).getByTestId("map-empty")).toHaveTextContent("No Upazila yet");
    expect(within(scene).queryByTestId(/^map-tasks-/)).not.toBeInTheDocument();
  });

  it("draws a phone-shaped map on a phone", async () => {
    setViewport(390);
    mockFetch(ROUTES);
    renderMap("/map?level=union&id=11");
    const scene = await screen.findByTestId("map-scene");
    const [, , width, height] = scene.getAttribute("viewBox")!.split(" ").map(Number);
    expect(width).toBe(380);
    expect(height!).toBeGreaterThan(width!); // nine Wards in two columns: tall, never wide
    expect(within(scene).getAllByTestId(/^map-building-ward-/)).toHaveLength(9);
  });

  it("says so when the place no longer exists", async () => {
    mockFetch({ "GET /api/map?level=union&id=99": { status: 404, body: { detail: "Union not found" } }, "GET /api/map?level=village": { body: VILLAGE } });
    const user = renderMap("/map?level=union&id=99");
    expect(await screen.findByRole("heading", { name: "This place is not on the map" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to the village" }));
    await waitFor(() => expect(screen.getByTestId("map-scene")).toHaveAttribute("data-level", "village"));
  });

  it("refreshes on its own and stops while the tab is hidden", async () => {
    const routes: Routes = { ...ROUTES };
    const { callsTo } = mockFetch(routes);
    renderMap("/map", 30);
    await screen.findByTestId("map-scene");
    routes["GET /api/map?level=village"] = { body: { ...VILLAGE, buildings: [CENTRAL, { ...STUDY, active_tasks: 4 }, BUSINESS] } };
    expect(await screen.findByTestId("map-tasks-upazila-1")).toHaveTextContent("4"); // new numbers without a reload

    setVisibility("hidden");
    const asked = callsTo("GET /api/map?level=village").length;
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(callsTo("GET /api/map?level=village")).toHaveLength(asked);
    setVisibility("visible");
    await waitFor(() => expect(callsTo("GET /api/map?level=village").length).toBeGreaterThan(asked));
  });
});
