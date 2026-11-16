import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import App from "../App";
import type { Agent } from "../api";
import { SessionProvider } from "../session";
import {
  AGENT_OPTIONS,
  AGENT_TEMPLATES,
  CENTRAL_MANAGER,
  DONE_TASK,
  HEALTH,
  MINA,
  STATS,
  STUDY_FULL,
  USER,
  VILLAGE,
  makeTree,
  mockFetch,
  ACTIVITY_ROUTE,
} from "./helpers";

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

function agentRoutes(agents: Agent[] = [CENTRAL_MANAGER, MINA]): Parameters<typeof mockFetch>[0] {
  return {
    "GET /api/setup/status": { body: { setup_completed: true } },
    "GET /api/auth/me": { body: USER },
    "GET /api/village": { body: VILLAGE },
    "GET /api/health": { body: HEALTH },
    "GET /api/stats/overview": { body: STATS },
    [ACTIVITY_ROUTE]: { body: [] },
    "GET /api/org/tree": { body: makeTree([STUDY_FULL]) },
    "GET /api/agent-templates": { body: AGENT_TEMPLATES },
    "GET /api/agent-options": { body: AGENT_OPTIONS },
    "GET /api/agents": { body: agents },
    "GET /api/tasks?agent_id=1": { body: [] },
    "GET /api/tasks?agent_id=2": { body: [] },
  };
}

const main = () => screen.getByRole("main");

describe("Agent Management", () => {
  it("lists the agents with avatar, role, office path and both badges", async () => {
    mockFetch(agentRoutes([CENTRAL_MANAGER, { ...MINA, lifecycle: "paused", runtime_state: "offline" }]));
    renderApp("/agents");

    const list = await screen.findByRole("group", { name: "Agents" });
    const cards = within(list).getAllByRole("link");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAccessibleName("Central Manager, Village Manager");
    expect(within(cards[0]!).getByText("Central Administration")).toBeInTheDocument();
    expect(cards[0]!.querySelector("svg[data-avatar]")).toHaveAttribute("data-avatar", "manager"); // drawn, not downloaded
    expect(document.querySelector("img")).toBeNull();

    const mina = cards[1]!;
    expect(mina).toHaveAttribute("href", "/agents/profile?id=2");
    expect(within(mina).getByRole("heading", { name: "Mina" })).toBeInTheDocument();
    expect(within(mina).getByText("Study Assistant")).toBeInTheDocument();
    expect(within(mina).getByText("Study Upazila › Academic Management › Ward 1: Class Routine")).toBeInTheDocument();
    expect(within(mina).getByTestId("lifecycle-badge")).toHaveTextContent("paused");
    expect(within(mina).getByTestId("runtime-badge")).toHaveTextContent("offline");
    expect(within(cards[0]!).getByTestId("lifecycle-badge")).toHaveTextContent("active");
    expect(screen.getByTestId("agent-count")).toHaveTextContent("2 agents");
  });

  it("filters by Upazila through the API", async () => {
    const { callsTo } = mockFetch({ ...agentRoutes(), "GET /api/agents?upazila_id=1": { body: [MINA] } });
    const user = renderApp("/agents");

    await screen.findByRole("group", { name: "Agents" });
    await user.selectOptions(screen.getByLabelText("Show agents of"), "Study Upazila");
    await waitFor(() => expect(callsTo("GET /api/agents?upazila_id=1")).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId("agent-count")).toHaveTextContent("1 agent in Study Upazila"));
    expect(within(screen.getByRole("group", { name: "Agents" })).getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "New agent" })).toHaveAttribute("href", "/agents/new?upazila=1");
  });

  it("says so when an Upazila has no agents", async () => {
    mockFetch({ ...agentRoutes(), "GET /api/agents?upazila_id=1": { body: [] } });
    renderApp("/agents?upazila=1");
    expect(await screen.findByRole("heading", { name: "Study Upazila has no agents yet" })).toBeInTheDocument();
  });
});

describe("New agent wizard", () => {
  it("creates an agent: template → name → office → responsibilities → tools → save & activate", async () => {
    const created: Agent = { ...MINA, id: 7, display_name: "Mina Akter", office_id: 1123 };
    const routes: Parameters<typeof mockFetch>[0] = {
      ...agentRoutes(),
      "POST /api/agents": () => {
        routes["GET /api/agents"] = { body: [CENTRAL_MANAGER, created] }; // what the server lists from now on
        return { status: 201, body: created };
      },
      "GET /api/tasks?agent_id=7": { body: [] },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderApp("/agents/new");
    const next = () => user.click(screen.getByRole("button", { name: "Next" }));

    // 1. template
    expect(await screen.findByRole("heading", { name: "Step 1 of 5: Template" })).toBeInTheDocument();
    await next();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a template.");
    await user.click(screen.getByRole("radio", { name: /Study Assistant/ }));
    await next();

    // 2. name (the template's name is suggested)
    const name = screen.getByLabelText("Agent name");
    expect(name).toHaveValue("Study Assistant");
    await user.clear(name);
    await next();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a name for the agent.");
    await user.type(name, "Mina Akter");
    await next();

    // 3. office: Upazila → Union → Ward
    await next();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the Office the agent will work in.");
    await user.selectOptions(screen.getByLabelText("Upazila"), "Study Upazila");
    expect(screen.getByLabelText("Union")).toHaveValue("11"); // the first Union and Ward are suggested
    expect(screen.getByLabelText("Ward")).toHaveValue("111");
    await user.selectOptions(screen.getByLabelText("Union"), "Course Learning");
    await user.selectOptions(screen.getByLabelText("Ward"), "Ward 3: Exam Preparation");
    expect(screen.getByText("Office: Exam Preparation Office")).toBeInTheDocument();
    await next();

    // 4. responsibilities + instructions, pre-filled from the template
    expect(screen.getByLabelText("Role")).toHaveValue("Study Assistant");
    expect(screen.getByLabelText("System instructions")).toHaveValue("You are a study assistant.");
    const responsibilities = screen.getByLabelText("Responsibilities");
    await user.clear(responsibilities);
    await user.type(responsibilities, "Exam plans only");
    await next();

    // 5. tools & permissions, with the honest note
    expect(screen.getByRole("note")).toHaveTextContent("Tools and permissions are enforced");
    expect(screen.getByRole("note")).toHaveTextContent("written to the audit log");
    expect(screen.getByRole("checkbox", { name: /Read permitted documents/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Read permitted documents/ })).toHaveAccessibleName(/not built yet/);
    expect(screen.getByRole("checkbox", { name: /Create task/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Spend money/ })).toHaveAccessibleName(/needs approval/);
    await user.click(screen.getByRole("checkbox", { name: /Read calendar/ })); // remove one
    await user.click(screen.getByRole("checkbox", { name: /Create task/ })); // add one
    expect(callsTo("POST /api/agents")).toHaveLength(0); // nothing is saved before the last button

    await user.click(screen.getByRole("button", { name: "Save & activate" }));
    await waitFor(() => expect(callsTo("POST /api/agents")).toHaveLength(1));
    expect(callsTo("POST /api/agents")[0]!.json).toEqual({
      template_id: 4,
      display_name: "Mina Akter",
      office_id: 1123, // the office of ward 123 = Course Learning, Ward 3
      role: "Study Assistant",
      description: "Exam plans only",
      system_instructions: "You are a study assistant.",
      allowed_tools: ["document.read", "task.create_child"],
      permissions: ["read_upazila_memory"],
      activate: true,
    });

    // it lands on the new agent's profile
    expect(await screen.findByRole("region", { name: "Agent Mina Akter" })).toBeInTheDocument();
  });

  it("goes back without losing what was entered and shows a server error", async () => {
    const { callsTo } = mockFetch({ ...agentRoutes(), "POST /api/agents": { status: 404, body: { detail: "Office not found" } } });
    const user = renderApp("/agents/new?upazila=1"); // opened from an Upazila: its first Ward office is preselected
    const next = () => user.click(screen.getByRole("button", { name: "Next" }));

    await user.click(await screen.findByRole("radio", { name: /Study Assistant/ }));
    await next();
    await next();
    expect(screen.getByLabelText("Upazila")).toHaveValue("1");
    expect(screen.getByLabelText("Ward")).toHaveValue("111");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("Agent name")).toHaveValue("Study Assistant");
    await next();
    await next();
    await next();
    await user.click(screen.getByRole("button", { name: "Save & activate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Office not found");
    expect(callsTo("POST /api/agents")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Step 5 of 5: Tools & permissions" })).toBeInTheDocument();
  });
});

describe("Agent Profile", () => {
  it("pauses, activates and disables an agent with the lifecycle buttons", async () => {
    const routes: Parameters<typeof mockFetch>[0] = {
      ...agentRoutes(),
      "POST /api/agents/2/pause": { body: {} },
      "POST /api/agents/2/activate": { body: {} },
      "POST /api/agents/2/disable": { body: {} },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderApp("/agents/profile?id=2");

    const card = await screen.findByRole("region", { name: "Agent Mina" });
    expect(within(card).getByTestId("lifecycle-badge")).toHaveTextContent("active");
    expect(within(card).queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();

    routes["GET /api/agents"] = { body: [CENTRAL_MANAGER, { ...MINA, lifecycle: "paused", runtime_state: "offline" }] };
    await user.click(within(card).getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(within(card).getByTestId("lifecycle-badge")).toHaveTextContent("paused"));
    expect(callsTo("POST /api/agents/2/pause")).toHaveLength(1);
    expect(within(card).queryByRole("button", { name: "Pause" })).not.toBeInTheDocument();

    routes["GET /api/agents"] = { body: [CENTRAL_MANAGER, MINA] };
    await user.click(within(card).getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(within(card).getByTestId("lifecycle-badge")).toHaveTextContent("active"));
    expect(callsTo("POST /api/agents/2/activate")).toHaveLength(1);

    routes["GET /api/agents"] = { body: [CENTRAL_MANAGER, { ...MINA, lifecycle: "disabled", runtime_state: "offline" }] };
    await user.click(within(card).getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(within(card).getByTestId("lifecycle-badge")).toHaveTextContent("disabled"));
    expect(callsTo("POST /api/agents/2/disable")).toHaveLength(1);
    expect(within(card).queryByRole("button", { name: "Disable" })).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Activate" })).toBeInTheDocument();
  });

  it("shows the server's reason when an action is refused", async () => {
    const homeless: Agent = { ...MINA, lifecycle: "disabled", runtime_state: "offline", office_id: null, location: null };
    mockFetch({
      ...agentRoutes([CENTRAL_MANAGER, homeless]),
      "POST /api/agents/2/activate": { status: 409, body: { detail: "This agent has no Office. Assign an Office before activating it." } },
    });
    const user = renderApp("/agents/profile?id=2");
    const card = await screen.findByRole("region", { name: "Agent Mina" });
    expect(within(card).getByText("No office — its office was deleted")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Activate" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Assign an Office before activating it.");
  });

  it("offers no lifecycle or delete buttons for the Central Manager", async () => {
    mockFetch(agentRoutes());
    renderApp("/agents/profile"); // no id: the first agent
    const card = await screen.findByRole("region", { name: "Agent Central Manager" });
    expect(within(card).getByText(/cannot be paused, disabled or deleted/)).toBeInTheDocument();
    for (const name of ["Pause", "Disable", "Activate", "Delete"]) {
      expect(within(card).queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(await screen.findByText("Office: Central Administration. The Central Manager cannot be moved.")).toBeInTheDocument();
  });

  it("shows the 409 reason when the server refuses to delete an agent", async () => {
    const reason = "'Mina' has task history, so it cannot be deleted. Disable it instead — its history is kept.";
    const { callsTo } = mockFetch({ ...agentRoutes(), "DELETE /api/agents/2": { status: 409, body: { detail: reason } } });
    const user = renderApp("/agents/profile?id=2");

    const card = await screen.findByRole("region", { name: "Agent Mina" });
    await user.click(within(card).getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Agent" });
    const confirm = within(dialog).getByRole("button", { name: "Delete Agent" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Type the name to confirm/), "Mina");
    await user.click(confirm);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(reason);
    expect(callsTo("DELETE /api/agents/2")[0]!.json).toEqual({ confirm_name: "Mina" });
    expect(screen.getByRole("region", { name: "Agent Mina" })).toBeInTheDocument(); // still there
  });

  it("deletes an agent without history and returns to the list; disables Delete when there is history", async () => {
    const routes: Parameters<typeof mockFetch>[0] = { ...agentRoutes(), "DELETE /api/agents/2": { body: { deleted: true } } };
    const { callsTo } = mockFetch(routes);
    const user = renderApp("/agents/profile?id=2");
    const card = await screen.findByRole("region", { name: "Agent Mina" });
    await user.click(within(card).getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Agent" });
    await user.type(within(dialog).getByLabelText(/Type the name to confirm/), "Mina");
    routes["GET /api/agents"] = { body: [CENTRAL_MANAGER] };
    await user.click(within(dialog).getByRole("button", { name: "Delete Agent" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Agent Management" })).toBeInTheDocument();
    expect(callsTo("DELETE /api/agents/2")).toHaveLength(1);
  });

  it("disables Delete and explains why when the agent has history, and lists that history", async () => {
    const child = DONE_TASK.children[0]!;
    mockFetch({ ...agentRoutes([CENTRAL_MANAGER, { ...MINA, has_history: true }]), "GET /api/tasks?agent_id=2": { body: [child] } });
    renderApp("/agents/profile?id=2");
    const card = await screen.findByRole("region", { name: "Agent Mina" });
    expect(within(card).getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(within(card).getByText(/cannot be deleted — disable it instead/)).toBeInTheDocument();

    const history = screen.getByRole("region", { name: "Task history" });
    const link = await within(history).findByRole("link", { name: "#2 help me prepare for my exam" });
    expect(link).toHaveAttribute("href", "/tasks?id=1"); // opens the request it belongs to
    expect(within(history).getByTestId("task-status")).toHaveTextContent("SUCCEEDED");
  });

  it("saves only the fields that were changed", async () => {
    const edited: Agent = {
      ...MINA,
      role: "Exam Coach",
      office_id: 1112,
      allowed_tools: ["document.read", "calendar.read", "task.create_child"],
      updated_at: "2026-11-15T11:00:00Z",
    };
    const routes: Parameters<typeof mockFetch>[0] = {
      ...agentRoutes(),
      "PATCH /api/agents/2": () => {
        routes["GET /api/agents"] = { body: [CENTRAL_MANAGER, edited] }; // what the server lists after the save
        return { body: edited };
      },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderApp("/agents/profile?id=2");

    const form = await screen.findByRole("form", { name: "Agent settings" });
    const save = within(form).getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    expect(within(form).getByLabelText("Agent name")).toHaveValue("Mina");
    expect(within(form).getByLabelText("Ward")).toHaveValue("111"); // its current office
    expect(within(form).getByRole("note")).toHaveTextContent("Tools and permissions are enforced");

    const role = within(form).getByLabelText("Role");
    await user.clear(role);
    await user.type(role, "Exam Coach");
    await user.click(within(form).getByRole("checkbox", { name: /Create task/ }));
    await user.selectOptions(within(form).getByLabelText("Ward"), "112"); // Ward 2: Assignment & Deadline
    await user.click(save);

    await waitFor(() => expect(callsTo("PATCH /api/agents/2")).toHaveLength(1));
    expect(callsTo("PATCH /api/agents/2")[0]!.json).toEqual({
      role: "Exam Coach",
      office_id: 1112,
      allowed_tools: ["document.read", "calendar.read", "task.create_child"],
    });
    // the form survives the reload: the confirmation shows and there is nothing left to save
    expect(await within(form).findByRole("status")).toHaveTextContent("Saved.");
    expect(save).toBeDisabled();
    expect(within(form).getByLabelText("Role")).toHaveValue("Exam Coach");
    expect(within(main()).getByRole("region", { name: "Agent Mina" })).toHaveTextContent("Exam Coach");
  });
});
