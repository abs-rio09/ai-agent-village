import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { TaskDetail } from "../api";
import { ACTIVITY_TEXT, ROBOT_OUTFITS, RobotAvatar, TEMPLATE_ROBOTS, robotLabel, robotRoleFor, type Activity, type RobotRole } from "../components/robots";
import AgentProfile from "../pages/AgentProfile";
import Agents from "../pages/Agents";
import Tasks from "../pages/Tasks";
import { AGENT_OPTIONS, AGENT_TEMPLATES, CENTRAL_MANAGER, MINA, STUDY_FULL, makeTask, makeTree, mockFetch } from "./helpers";

// The 15 agent templates of docs/SPEC.md §6 (backend/app/agent_catalog.py), in the SPEC's order.
const TEMPLATE_KEYS = [
  "village_manager", "office_manager", "pion_helper", "study_assistant", "teacher_tutor", "research_librarian",
  "business_manager", "sales_assistant", "customer_support", "accountant", "daily_reporter", "doctor_wellness",
  "repair_technician", "technical_support", "project_manager",
];
const ROLES: RobotRole[] = ["manager", "pion", "doctor", "technician", "researcher", "sales", "default"];
const STATUSES: Activity[] = ["working", "idle", "waiting", "offline"];

describe("robot roles", () => {
  it("maps every one of the 15 templates to a robot, in one table", () => {
    expect(Object.keys(TEMPLATE_ROBOTS).sort()).toEqual([...TEMPLATE_KEYS].sort());
    for (const key of TEMPLATE_KEYS) {
      expect(ROLES).toContain(robotRoleFor(key));
      expect(robotRoleFor(key)).not.toBe("default"); // every template has its own outfit
    }
    // the roles the SPEC names
    expect(robotRoleFor("village_manager")).toBe("manager");
    expect(robotRoleFor("pion_helper")).toBe("pion");
    expect(robotRoleFor("doctor_wellness")).toBe("doctor");
    expect(robotRoleFor("repair_technician")).toBe("technician");
    expect(robotRoleFor("research_librarian")).toBe("researcher");
    expect(robotRoleFor("sales_assistant")).toBe("sales");
    // no template, or one that does not exist: the plain robot
    for (const key of [null, undefined, "", "pirate"]) expect(robotRoleFor(key)).toBe("default");
    expect(Object.keys(ROBOT_OUTFITS).sort()).toEqual([...ROLES].sort());
    expect(new Set(Object.values(TEMPLATE_ROBOTS))).toEqual(new Set(ROLES.filter((role) => role !== "default"))); // each outfit is used
  });
});

describe("RobotAvatar", () => {
  it.each(ROLES)("draws the %s robot in SVG with its role and an accessible label", (role) => {
    render(<RobotAvatar role={role} status="idle" name="Mina" title="Study Assistant" size={64} />);
    const avatar = screen.getByRole("img");
    expect(avatar).toHaveAttribute("data-robot", role);
    expect(avatar).toHaveAccessibleName(role === "doctor" ? "Mina, Study Assistant, assistant only, idle" : "Mina, Study Assistant, idle");
    expect(avatar.querySelector("svg")).not.toBeNull();
    expect(avatar.querySelector("img, image")).toBeNull(); // nothing is downloaded
    expect(avatar).toHaveAttribute("title", expect.stringContaining(ROBOT_OUTFITS[role]));
  });

  it("draws a different outfit for every role", () => {
    const markup = ROLES.map((role) => {
      const { container, unmount } = render(<RobotAvatar role={role} />);
      const svg = container.querySelector("svg")!.innerHTML;
      unmount();
      return svg;
    });
    expect(new Set(markup).size).toBe(ROLES.length);
  });

  it.each(STATUSES)("shows the %s status in the label and on the indicator", (status) => {
    render(<RobotAvatar role="researcher" status={status} name="Mina" title="Study Assistant" taskId={5} size={56} />);
    const avatar = screen.getByRole("img");
    expect(avatar).toHaveAttribute("data-status", status);
    const expected = {
      working: "Mina, Study Assistant, working on task #5",
      idle: "Mina, Study Assistant, idle (task #5)",
      waiting: "Mina, Study Assistant, waiting for your approval (task #5)",
      offline: "Mina, Study Assistant, offline (task #5)",
    }[status];
    expect(avatar).toHaveAccessibleName(expected);
    expect(within(avatar).getByTestId("robot-status-dot")).toBeInTheDocument();
    // the current-task badge: for a working or waiting agent, never for an offline one
    if (status === "offline") expect(within(avatar).queryByTestId("robot-task-badge")).not.toBeInTheDocument();
    else expect(within(avatar).getByTestId("robot-task-badge")).toHaveTextContent("#5");
    expect(ACTIVITY_TEXT[status]).toBeTruthy();
  });

  it("labels the doctor robot as an assistant only", () => {
    render(<RobotAvatar role="doctor" status="idle" name="Dr. Bot" title="General Wellness Assistant" size={72} />);
    const avatar = screen.getByRole("img");
    expect(avatar).toHaveAccessibleName("Dr. Bot, General Wellness Assistant, assistant only, idle");
    expect(within(avatar).getByText("assistant only")).toBeInTheDocument(); // written on the avatar too
    expect(avatar).toHaveAttribute("title", expect.stringContaining("not a doctor"));
  });

  it("is decoration without a name: hidden from assistive technology, no status, no badge", () => {
    const { container } = render(<RobotAvatar role="sales" size={36} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    const avatar = container.querySelector("[data-robot]")!;
    expect(avatar).toHaveAttribute("aria-hidden", "true");
    expect(within(avatar as HTMLElement).queryByTestId("robot-status-dot")).not.toBeInTheDocument();
    expect(robotLabel({ role: "sales" })).toBe("");
  });
});

describe("robots on the pages", () => {
  const WORKING = { ...MINA, activity: "working" as const, current_task_id: 12 };
  const WAITING = { ...MINA, id: 3, display_name: "Sumi", role: "Customer Support Agent", template_key: "customer_support", activity: "waiting" as const, current_task_id: 14 };
  const OFFLINE = { ...MINA, id: 4, display_name: "Rafi", lifecycle: "paused" as const, activity: "offline" as const, runtime_state: "offline" as const };

  it("shows each agent as its role's robot with the activity the server computed", async () => {
    mockFetch({ "GET /api/agents": { body: [CENTRAL_MANAGER, WORKING, WAITING, OFFLINE] }, "GET /api/org/tree": { body: makeTree([STUDY_FULL]) } });
    render(
      <MemoryRouter initialEntries={["/agents"]}>
        <Routes>
          <Route path="/agents" element={<Agents />} />
        </Routes>
      </MemoryRouter>,
    );
    const manager = await screen.findByRole("img", { name: "Central Manager, Village Manager, idle" });
    expect(manager).toHaveAttribute("data-robot", "manager");
    const mina = screen.getByRole("img", { name: "Mina, Study Assistant, working on task #12" });
    expect(mina).toHaveAttribute("data-robot", "researcher");
    expect(within(mina).getByTestId("robot-task-badge")).toHaveTextContent("#12");
    const sumi = screen.getByRole("img", { name: "Sumi, Customer Support Agent, waiting for your approval (task #14)" });
    expect(sumi).toHaveAttribute("data-robot", "sales");
    expect(screen.getByRole("img", { name: "Rafi, Study Assistant, offline" })).toHaveAttribute("data-status", "offline");
    // the badge next to it says the same
    const card = screen.getByRole("link", { name: "Sumi, Customer Support Agent" });
    expect(within(card).getByTestId("runtime-badge")).toHaveTextContent("waiting");
  });

  it("shows the robot, the activity and the current task on the agent's profile", async () => {
    mockFetch({
      "GET /api/agents": { body: [CENTRAL_MANAGER, WORKING] },
      "GET /api/agents/2": { body: WORKING },
      "GET /api/org/tree": { body: makeTree([STUDY_FULL]) },
      "GET /api/agent-options": { body: AGENT_OPTIONS },
      "GET /api/agent-templates": { body: AGENT_TEMPLATES },
      "GET /api/tasks?agent_id=2&limit=20": { body: [] },
    });
    render(
      <MemoryRouter initialEntries={["/agents/profile?id=2"]}>
        <Routes>
          <Route path="/agents/profile" element={<AgentProfile timezone="Asia/Dhaka" />} />
          <Route path="/tasks" element={<p>task center</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const panel = await screen.findByRole("region", { name: "Agent Mina" });
    expect(within(panel).getByRole("img", { name: "Mina, Study Assistant, working on task #12" })).toHaveAttribute("data-robot", "researcher");
    expect(within(panel).getByRole("link", { name: "works on task #12" })).toHaveAttribute("href", "/tasks?id=12");
  });

  it("shows the agent of a child task in the Task Center, waiting when its task waits", async () => {
    const parent = makeTask({ id: 11, status: "RUNNING", child_count: 1, pending_approval_id: 7 });
    const child = makeTask({
      id: 12, parent_task_id: 11, depth: 1, status: "WAITING_APPROVAL", pending_approval_id: 7,
      assigned_agent: { id: 3, display_name: "Sumi", role: "Customer Support Agent", avatar_key: "support", template_key: "customer_support", is_central_manager: false },
    });
    const detail: TaskDetail = { ...parent, children: [child], messages: [] };
    mockFetch({ "GET /api/tasks?top_level=true": { body: [parent] }, "GET /api/tasks/11": { body: detail } });
    render(
      <MemoryRouter initialEntries={["/tasks?id=11"]}>
        <Routes>
          <Route path="/tasks" element={<Tasks timezone="Asia/Dhaka" pollMs={60_000} />} />
        </Routes>
      </MemoryRouter>,
    );
    const row = await screen.findByRole("listitem", { name: "Child task 12" });
    const robot = within(row).getByRole("img", { name: "Sumi, Customer Support Agent, waiting for your approval (task #12)" });
    expect(robot).toHaveAttribute("data-robot", "sales");
    expect(robot).toHaveAttribute("data-status", "waiting");
  });
});
