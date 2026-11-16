import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { MemoryEntry, Schedule, SchedulesPage } from "../api";
import MemoryPage from "../pages/Memory";
import Schedules from "../pages/Schedules";
import Tasks from "../pages/Tasks";
import { CENTRAL_MANAGER, GARDEN, MINA, STUDY_EMPTY, makeTask, makeTree, mockFetch } from "./helpers";

type Routes = Parameters<typeof mockFetch>[0];

function makeMemory(overrides: Partial<MemoryEntry> = {}): MemoryEntry {
  return {
    id: 1,
    scope: "VILLAGE",
    upazila_id: null,
    upazila_name: null,
    agent_id: null,
    agent_name: null,
    title: "Office hours",
    content: "The village works from 9 to 5.",
    contains_customer_data: false,
    created_by: "chairman:chairman",
    updated_by: "chairman:chairman",
    created_at: "2026-11-16T10:00:00Z",
    updated_at: "2026-11-16T10:00:00Z",
    ...overrides,
  };
}

function makeSchedule(overrides: Partial<Schedule> = {}): Schedule {
  return {
    id: 3,
    name: "Summarise today's study progress",
    kind: "custom",
    builtin_key: null,
    agent: { id: 2, display_name: "Mina", role: "Study Assistant", avatar_key: "student", is_central_manager: false },
    request_text: "Summarise today's study progress",
    trigger_type: "interval",
    interval_minutes: 1,
    daily_time: null,
    trigger_text: "every minute",
    paused: false,
    last_run_at: "2026-11-16T10:00:00Z",
    last_task_id: 14,
    last_task_status: "SUCCEEDED",
    next_run_at: "2026-11-16T10:01:00Z",
    created_at: "2026-11-16T09:59:00Z",
    ...overrides,
  };
}

const HEALTH_CHECK = makeSchedule({
  id: 1,
  name: "Agent health check",
  kind: "builtin",
  builtin_key: "health_check",
  agent: null,
  request_text: "Marks tasks that have been RUNNING without progress for too long as FAILED.",
  interval_minutes: 10,
  trigger_text: "every 10 minutes",
  last_run_at: null,
  last_task_id: null,
  last_task_status: null,
});
const DAILY = makeSchedule({
  id: 2,
  name: "Daily report",
  kind: "builtin",
  builtin_key: "daily_report",
  agent: null,
  request_text: "Creates the daily summary task.",
  trigger_type: "daily",
  interval_minutes: null,
  daily_time: "21:00",
  trigger_text: "every day at 21:00",
  last_run_at: null,
  last_task_id: null,
  last_task_status: null,
});

function schedulesPage(schedules: Schedule[], overrides: Partial<SchedulesPage> = {}): SchedulesPage {
  return { scheduler_running: true, timezone: "Asia/Dhaka", schedules, ...overrides };
}

function renderMemory(path = "/memory") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/memory" element={<MemoryPage timezone="Asia/Dhaka" />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

function renderSchedules() {
  render(
    <MemoryRouter initialEntries={["/schedules"]}>
      <Routes>
        <Route path="/schedules" element={<Schedules timezone="Asia/Dhaka" pollMs={60_000} />} />
        <Route path="/tasks" element={<p>task center</p>} />
        <Route path="/agents/profile" element={<p>agent profile</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const VILLAGE = "GET /api/memory?scope=VILLAGE";
const UPAZILA = "GET /api/memory?scope=UPAZILA";
const AGENT = "GET /api/memory?scope=AGENT";

describe("Memory & Knowledge Center", () => {
  it("lists the three scopes, one tab each", async () => {
    const { callsTo } = mockFetch({
      [VILLAGE]: { body: [makeMemory()] },
      [UPAZILA]: { body: [makeMemory({ id: 2, scope: "UPAZILA", upazila_id: 1, upazila_name: "Study Upazila", title: "Study plan" })] },
      [`${UPAZILA}&upazila_id=2`]: { body: [] },
      [AGENT]: {
        body: [
          makeMemory({
            id: 3, scope: "AGENT", agent_id: 2, agent_name: "Mina", title: "Customer Rahim", content: "call 01712-345678",
            contains_customer_data: true, created_by: "agent:2", updated_by: "agent:2",
          }),
        ],
      },
      "GET /api/org/tree": { body: makeTree([STUDY_EMPTY, GARDEN]) },
      "GET /api/agents": { body: [CENTRAL_MANAGER, MINA] },
    });
    const user = renderMemory();

    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Village", "Upazila", "Agent"]);
    expect(screen.getByRole("tab", { name: "Village" })).toHaveAttribute("aria-selected", "true");
    const village = await screen.findByRole("listitem", { name: "Memory 1" });
    expect(village).toHaveTextContent("Office hours");
    expect(village).toHaveTextContent("The village works from 9 to 5.");
    expect(village).toHaveTextContent("Whole village · by Chairman (chairman)");
    expect(screen.getByRole("note")).toHaveTextContent("Customer data never goes into Village memory");
    expect(screen.queryByLabelText("Upazila")).not.toBeInTheDocument(); // village memory has no owner

    await user.click(screen.getByRole("tab", { name: "Upazila" }));
    expect(await screen.findByRole("listitem", { name: "Memory 2" })).toHaveTextContent("Study Upazila · by Chairman (chairman)");
    await user.selectOptions(await screen.findByLabelText("Upazila"), "Garden");
    await waitFor(() => expect(callsTo(`${UPAZILA}&upazila_id=2`)).toHaveLength(1));
    expect(await screen.findByRole("heading", { name: "No Upazila memory yet" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Agent" }));
    const note = await screen.findByRole("listitem", { name: "Memory 3" });
    expect(note).toHaveTextContent("customer data");
    expect(note).toHaveTextContent("Mina · by Mina"); // written by the agent itself
  });

  it("adds a village memory and shows the server's refusal of customer data", async () => {
    const routes: Routes = {
      [VILLAGE]: { body: [] },
      "POST /api/memory": {
        status: 422,
        body: { detail: [{ loc: ["body", "contains_customer_data"], msg: "Customer data cannot be stored in Village memory, because the whole village can read it.", type: "value_error" }] },
      },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderMemory();

    await user.click(await screen.findByRole("button", { name: "Add memory" }));
    const dialog = screen.getByRole("dialog", { name: "New Village memory" });
    expect(dialog).toHaveTextContent("must not contain customer data");
    expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument(); // the flag cannot even be set for Village memory
    await user.click(within(dialog).getByRole("button", { name: "Add memory" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("A memory needs a title and a text.");
    expect(callsTo("POST /api/memory")).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Title"), "Rahim");
    await user.type(within(dialog).getByLabelText("Text"), "call 01712-345678");
    await user.click(within(dialog).getByRole("button", { name: "Add memory" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Customer data cannot be stored in Village memory");
    expect(callsTo("POST /api/memory")[0]!.json).toEqual({
      scope: "VILLAGE", upazila_id: null, agent_id: null, title: "Rahim", content: "call 01712-345678", contains_customer_data: false,
    });

    // an acceptable text is saved and the list reloads
    routes["POST /api/memory"] = { status: 201, body: makeMemory({ id: 9, title: "Rahim" }) };
    routes[VILLAGE] = { body: [makeMemory({ id: 9, title: "Holiday", content: "Closed on Friday" })] };
    await user.clear(within(dialog).getByLabelText("Text"));
    await user.type(within(dialog).getByLabelText("Text"), "Closed on Friday");
    await user.click(within(dialog).getByRole("button", { name: "Add memory" }));
    expect(await screen.findByRole("listitem", { name: "Memory 9" })).toHaveTextContent("Closed on Friday");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("adds an agent memory for a chosen agent, with the customer-data flag", async () => {
    const { callsTo } = mockFetch({
      [AGENT]: { body: [] },
      "GET /api/agents": { body: [CENTRAL_MANAGER, MINA] },
      "POST /api/memory": { status: 201, body: makeMemory({ id: 4, scope: "AGENT", agent_id: 2 }) },
    });
    const user = renderMemory("/memory?scope=AGENT");
    await screen.findByRole("heading", { name: "No Agent memory yet" });
    await user.click(screen.getByRole("button", { name: "Add memory" }));
    const dialog = screen.getByRole("dialog", { name: "New Agent memory" });
    await user.selectOptions(within(dialog).getByLabelText("Agent"), "Mina (Study Assistant)");
    await user.type(within(dialog).getByLabelText("Title"), "Customer Rahim");
    await user.type(within(dialog).getByLabelText("Text"), "prefers evening delivery");
    await user.click(within(dialog).getByRole("checkbox", { name: /Contains customer data/ }));
    await user.click(within(dialog).getByRole("button", { name: "Add memory" }));
    await waitFor(() => expect(callsTo("POST /api/memory")).toHaveLength(1));
    expect(callsTo("POST /api/memory")[0]!.json).toEqual({
      scope: "AGENT", upazila_id: null, agent_id: 2, title: "Customer Rahim", content: "prefers evening delivery", contains_customer_data: true,
    });
  });

  it("views and edits a memory, and deletes one after a confirm step", async () => {
    const routes: Routes = {
      [VILLAGE]: { body: [makeMemory()] },
      "PATCH /api/memory/1": { body: makeMemory({ content: "The village works from 8 to 4." }) },
      "DELETE /api/memory/1": { body: { deleted: true } },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderMemory();

    await user.click(await screen.findByRole("button", { name: "View / edit" }));
    const dialog = screen.getByRole("dialog", { name: "Memory" });
    expect(within(dialog).getByLabelText("Title")).toHaveValue("Office hours");
    expect(within(dialog).getByLabelText("Text")).toHaveValue("The village works from 9 to 5.");
    expect(dialog).toHaveTextContent("Village memory · written by Chairman (chairman)");
    await user.clear(within(dialog).getByLabelText("Text"));
    await user.type(within(dialog).getByLabelText("Text"), "The village works from 8 to 4.");
    routes[VILLAGE] = { body: [makeMemory({ content: "The village works from 8 to 4." })] };
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(callsTo("PATCH /api/memory/1")).toHaveLength(1));
    expect(callsTo("PATCH /api/memory/1")[0]!.json).toEqual({ title: "Office hours", content: "The village works from 8 to 4.", contains_customer_data: false });
    expect(await screen.findByText("The village works from 8 to 4.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirm = screen.getByRole("dialog", { name: "Delete this memory?" });
    expect(confirm).toHaveTextContent("Office hours is removed for good.");
    expect(callsTo("DELETE /api/memory/1")).toHaveLength(0); // not before confirming
    routes[VILLAGE] = { body: [] };
    await user.click(within(confirm).getByRole("button", { name: "Delete memory" }));
    await waitFor(() => expect(callsTo("DELETE /api/memory/1")).toHaveLength(1));
    expect(await screen.findByRole("heading", { name: "No Village memory yet" })).toBeInTheDocument();
  });
});

describe("Schedules", () => {
  const LIST = "GET /api/schedules";
  const AGENTS = "GET /api/agents";

  it("lists built-in and own schedules with last and next run", async () => {
    mockFetch({ [LIST]: { body: schedulesPage([HEALTH_CHECK, DAILY, makeSchedule()]) }, [AGENTS]: { body: [CENTRAL_MANAGER, MINA] } });
    renderSchedules();

    const health = await screen.findByRole("listitem", { name: "Schedule 1" });
    expect(health).toHaveTextContent("Agent health check");
    expect(health).toHaveTextContent("built-in");
    expect(health).toHaveTextContent("every 10 minutes — Marks tasks that have been RUNNING");
    expect(health).toHaveTextContent("Last run:never");
    expect(within(health).getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(within(health).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument(); // built-in: pause only
    expect(screen.getByRole("listitem", { name: "Schedule 2" })).toHaveTextContent("every day at 21:00");

    const own = screen.getByRole("listitem", { name: "Schedule 3" });
    expect(own).toHaveTextContent("every minute → task for Mina: “Summarise today's study progress”");
    expect(within(own).getByTestId("schedule-state")).toHaveTextContent("active");
    expect(within(own).getByRole("link", { name: "task #14" })).toHaveAttribute("href", "/tasks?id=14");
    expect(within(own).getByTestId("task-status")).toHaveTextContent("SUCCEEDED");
    expect(within(own).getByTestId("next-run")).not.toHaveTextContent("—");
    expect(within(own).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // the scheduler is running
    // the Central Manager only routes: it is not offered as the agent of a schedule
    expect(within(screen.getByLabelText("Agent")).getAllByRole("option").map((option) => option.textContent)).toEqual(["Mina (Study Assistant)"]);
  });

  it("says so when the scheduler is not running", async () => {
    mockFetch({ [LIST]: { body: schedulesPage([HEALTH_CHECK], { scheduler_running: false }) }, [AGENTS]: { body: [] } });
    renderSchedules();
    expect(await screen.findByRole("alert")).toHaveTextContent("The scheduler is not running, so no schedule creates tasks right now.");
  });

  it("creates an interval schedule and a daily one", async () => {
    const routes: Routes = {
      [LIST]: { body: schedulesPage([HEALTH_CHECK, DAILY]) },
      [AGENTS]: { body: [CENTRAL_MANAGER, MINA] },
      "POST /api/schedules": { status: 201, body: makeSchedule() },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderSchedules();
    const form = await screen.findByRole("form", { name: "New schedule" });
    await within(form).findByRole("option", { name: "Mina (Study Assistant)" });

    await user.click(within(form).getByRole("button", { name: "Create schedule" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Write what the agent should do.");
    await user.type(within(form).getByLabelText("Request"), "Summarise today's study progress");
    const minutes = within(form).getByLabelText("Interval in minutes");
    await user.clear(minutes);
    await user.click(within(form).getByRole("button", { name: "Create schedule" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("between 1 and 10080 minutes");
    expect(callsTo("POST /api/schedules")).toHaveLength(0);

    await user.type(minutes, "1");
    routes[LIST] = { body: schedulesPage([HEALTH_CHECK, DAILY, makeSchedule({ last_run_at: null, last_task_id: null, last_task_status: null })]) };
    await user.click(within(form).getByRole("button", { name: "Create schedule" }));
    await waitFor(() => expect(callsTo("POST /api/schedules")).toHaveLength(1));
    expect(callsTo("POST /api/schedules")[0]!.json).toEqual({
      agent_id: 2, request_text: "Summarise today's study progress", trigger_type: "interval", interval_minutes: 1,
    });
    expect(await screen.findByRole("listitem", { name: "Schedule 3" })).toBeInTheDocument();
    expect(within(form).getByLabelText("Request")).toHaveValue("");

    await user.type(within(form).getByLabelText("Request"), "Plan tomorrow");
    await user.click(within(form).getByRole("radio", { name: /Every day at/ }));
    await user.click(within(form).getByRole("button", { name: "Create schedule" }));
    await waitFor(() => expect(callsTo("POST /api/schedules")).toHaveLength(2));
    expect(callsTo("POST /api/schedules")[1]!.json).toEqual({ agent_id: 2, request_text: "Plan tomorrow", trigger_type: "daily", daily_time: "09:00" });
  });

  it("pauses, resumes and deletes (after a confirm step)", async () => {
    const routes: Routes = {
      [LIST]: { body: schedulesPage([makeSchedule()]) },
      [AGENTS]: { body: [MINA] },
      "POST /api/schedules/3/pause": { body: makeSchedule({ paused: true, next_run_at: null }) },
      "POST /api/schedules/3/resume": { body: makeSchedule() },
      "DELETE /api/schedules/3": { body: { deleted: true } },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderSchedules();
    const row = () => screen.getByRole("listitem", { name: "Schedule 3" });

    await screen.findByRole("listitem", { name: "Schedule 3" });
    routes[LIST] = { body: schedulesPage([makeSchedule({ paused: true, next_run_at: null })]) };
    await user.click(within(row()).getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(within(row()).getByTestId("schedule-state")).toHaveTextContent("paused"));
    expect(within(row()).getByTestId("next-run")).toHaveTextContent("paused");
    expect(callsTo("POST /api/schedules/3/pause")).toHaveLength(1);

    routes[LIST] = { body: schedulesPage([makeSchedule()]) };
    await user.click(within(row()).getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(within(row()).getByTestId("schedule-state")).toHaveTextContent("active"));
    expect(callsTo("POST /api/schedules/3/resume")).toHaveLength(1);

    await user.click(within(row()).getByRole("button", { name: "Delete" }));
    const confirm = screen.getByRole("dialog", { name: "Delete this schedule?" });
    expect(confirm).toHaveTextContent("will create no more tasks. The tasks it already created are kept.");
    expect(callsTo("DELETE /api/schedules/3")).toHaveLength(0);
    routes[LIST] = { body: schedulesPage([]) };
    await user.click(within(confirm).getByRole("button", { name: "Delete schedule" }));
    await waitFor(() => expect(callsTo("DELETE /api/schedules/3")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Schedule 3" })).not.toBeInTheDocument());
  });
});

describe("Task Center and scheduled tasks", () => {
  it("says that a scheduled task went straight to its agent", async () => {
    const task = makeTask({
      id: 14,
      kind: "scheduled",
      status: "SUCCEEDED",
      created_by: "schedule:3",
      created_by_name: "schedule:3",
      assigned_agent: { id: 2, display_name: "Mina", role: "Study Assistant", avatar_key: "student", is_central_manager: false },
      output: "[Demo] Mina (Study Assistant)",
    });
    mockFetch({ "GET /api/tasks?top_level=true": { body: [task] }, "GET /api/tasks/14": { body: { ...task, children: [], messages: [] } } });
    render(
      <MemoryRouter initialEntries={["/tasks?id=14"]}>
        <Routes>
          <Route path="/tasks" element={<Tasks timezone="Asia/Dhaka" pollMs={60_000} />} />
        </Routes>
      </MemoryRouter>,
    );
    const routing = await screen.findByRole("region", { name: "Routing result" });
    expect(routing).toHaveTextContent("Created by a schedule and given directly to Mina. The Central Manager did not route it.");
  });
});
