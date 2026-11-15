import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { TaskDetail } from "../api";
import Tasks from "../pages/Tasks";
import { DONE_TASK, makeTask, mockFetch } from "./helpers";

const POLL = 25; // ms — fast, so the tests can watch the polling start and stop

function renderTasks(path = "/tasks") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tasks" element={<Tasks timezone="Asia/Dhaka" pollMs={POLL} />} />
        <Route path="/agents/profile" element={<p>agent profile</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const LIST = "GET /api/tasks?top_level=true";
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("Task Center", () => {
  it("sends a request to the Central Manager and shows it in the list", async () => {
    const queued = makeTask({ id: 5, title: "help me prepare for my exam", description: "Physics" });
    const detail: TaskDetail = { ...queued, children: [], messages: [] };
    const routes: Parameters<typeof mockFetch>[0] = {
      [LIST]: { body: [] },
      "POST /api/tasks": { status: 201, body: queued },
      "GET /api/tasks/5": { body: detail },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderTasks();

    expect(await screen.findByText("No requests yet. Send the first one above.")).toBeInTheDocument();
    const form = screen.getByRole("form", { name: "Send to Central Manager" });
    await user.click(within(form).getByRole("button", { name: "Send to Central Manager" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Write what you need.");
    expect(callsTo("POST /api/tasks")).toHaveLength(0);

    await user.type(within(form).getByLabelText("Request"), "  help me prepare for my exam ");
    await user.type(within(form).getByLabelText("Details (optional)"), "Physics");
    await user.selectOptions(within(form).getByLabelText("Priority"), "High");
    routes[LIST] = { body: [queued] }; // what the server lists after the POST
    await user.click(within(form).getByRole("button", { name: "Send to Central Manager" }));

    await waitFor(() => expect(callsTo("POST /api/tasks")).toHaveLength(1));
    expect(callsTo("POST /api/tasks")[0]!.json).toEqual({ title: "help me prepare for my exam", description: "Physics", priority: "high" });

    const list = screen.getByRole("region", { name: "Tasks" });
    const row = await within(list).findByRole("link", { name: /#5 help me prepare for my exam/ });
    expect(within(row).getByTestId("task-status")).toHaveTextContent("QUEUED");
    expect(row).toHaveAttribute("aria-current", "true"); // the new request is opened
    expect(within(form).getByLabelText("Request")).toHaveValue("");

    const panel = await screen.findByRole("region", { name: "Task 5" });
    expect(within(panel).getByText("Waiting for the Central Manager to route this request…")).toBeInTheDocument();
    expect(within(panel).getByText("not assigned yet")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Cancel task" })).toBeInTheDocument();
  });

  it("renders the routing result, child tasks, agent messages, output and timestamps of a task", async () => {
    mockFetch({ [LIST]: { body: [DONE_TASK] }, "GET /api/tasks/1": { body: DONE_TASK } });
    renderTasks("/tasks?id=1");

    const panel = await screen.findByRole("region", { name: "Task 1" });
    expect(within(panel).getByRole("heading", { name: "help me prepare for my exam" })).toBeInTheDocument();
    expect(within(panel).getAllByTestId("task-status")[0]).toHaveTextContent("SUCCEEDED");
    expect(within(panel).queryByRole("button", { name: "Cancel task" })).not.toBeInTheDocument(); // finished

    const routing = within(panel).getByRole("region", { name: "Routing result" });
    expect(routing).toHaveTextContent("Routed to Study Upazila (matched keywords: exam) and delegated to Mina (Study Assistant)");
    expect(routing).toHaveTextContent("Study Upazila › Academic Management › Ward 1: Class Routine");
    expect(routing).toHaveTextContent("not by an AI model");
    expect(within(routing).getByRole("link", { name: "Mina" })).toHaveAttribute("href", "/agents/profile?id=2");

    const children = within(panel).getByRole("region", { name: "Child tasks" });
    const child = within(children).getByRole("listitem", { name: "Child task 2" });
    expect(within(child).getByRole("link", { name: "Mina" })).toBeInTheDocument();
    expect(within(child).getByTestId("task-status")).toHaveTextContent("SUCCEEDED");
    expect(within(child).getByText(/^\[Demo\] Mina \(Study Assistant\)/)).toBeInTheDocument();

    const messages = within(panel).getByRole("region", { name: "Agent messages" });
    const items = within(messages).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("delegation");
    expect(items[0]).toHaveTextContent("Central Manager → Mina");
    expect(items[0]).toHaveTextContent("Delegated the task (task #2)");
    expect(items[1]).toHaveTextContent("result");
    expect(items[1]).toHaveTextContent("Mina → Central Manager");
    expect(items[1]).toHaveTextContent("Returned its result");

    expect(within(panel).getByText(/^\[Demo\] Central Manager report/)).toBeInTheDocument(); // final output
    expect(within(panel).getByText("Created by")).toBeInTheDocument();
    for (const name of ["Created", "Started", "Completed"]) {
      expect(within(panel).getByText(name).nextElementSibling).toHaveTextContent(/2026/); // real timestamps
    }
    expect(within(panel).queryByRole("alert")).not.toBeInTheDocument(); // no error
  });

  it("shows the error of a failed request", async () => {
    const reason = "The Central Manager could not tell which Upazila this request belongs to.";
    const failed: TaskDetail = { ...makeTask({ id: 3, title: "hello there", status: "FAILED", error: reason }), children: [], messages: [] };
    mockFetch({ [LIST]: { body: [failed] }, "GET /api/tasks/3": { body: failed } });
    renderTasks("/tasks?id=3");

    const panel = await screen.findByRole("region", { name: "Task 3" });
    expect(within(panel).getByRole("alert")).toHaveTextContent(reason);
    expect(within(panel).getByText("The request was not delegated. The reason is shown under “Error”.")).toBeInTheDocument();
    expect(within(panel).getByText("No task has been delegated.")).toBeInTheDocument();
    expect(within(panel).getByText("No messages yet.")).toBeInTheDocument();
  });

  it("polls while a task is unfinished and stops when nothing is active", async () => {
    const running = makeTask({ id: 1, status: "RUNNING" });
    const routes: Parameters<typeof mockFetch>[0] = { [LIST]: { body: [running] } };
    const { callsTo } = mockFetch(routes);
    renderTasks();

    await screen.findByRole("link", { name: /#1 help me prepare/ });
    expect(screen.getByTestId("poll-state")).toHaveTextContent("updating automatically…");
    await waitFor(() => expect(callsTo(LIST).length).toBeGreaterThanOrEqual(3)); // it keeps asking

    routes[LIST] = { body: [makeTask({ id: 1, status: "SUCCEEDED" })] }; // the worker finished the task
    await waitFor(() => expect(screen.getByTestId("poll-state")).toHaveTextContent("up to date"));
    expect(screen.getByTestId("task-status")).toHaveTextContent("SUCCEEDED");
    const settled = callsTo(LIST).length;
    await pause(POLL * 8);
    expect(callsTo(LIST)).toHaveLength(settled); // not one more request
  });

  it("does not poll at all when every task is finished", async () => {
    const { callsTo } = mockFetch({ [LIST]: { body: [DONE_TASK] } });
    renderTasks();
    await screen.findByRole("link", { name: /#1 help me prepare/ });
    await pause(POLL * 8);
    expect(callsTo(LIST)).toHaveLength(1);
    expect(screen.getByTestId("poll-state")).toHaveTextContent("up to date");
  });

  it("cancels a running task", async () => {
    const running: TaskDetail = { ...makeTask({ id: 1, status: "RUNNING" }), children: [], messages: [] };
    const cancelled: TaskDetail = { ...running, status: "CANCELLED", completed_at: "2026-11-15T10:00:05Z" };
    const routes: Parameters<typeof mockFetch>[0] = {
      [LIST]: { body: [running] },
      "GET /api/tasks/1": { body: running },
      "POST /api/tasks/1/cancel": () => {
        routes[LIST] = { body: [cancelled] };
        routes["GET /api/tasks/1"] = { body: cancelled };
        return { body: cancelled };
      },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderTasks("/tasks?id=1");

    const panel = await screen.findByRole("region", { name: "Task 1" });
    await user.click(within(panel).getByRole("button", { name: "Cancel task" }));
    await waitFor(() => expect(within(panel).getAllByTestId("task-status")[0]).toHaveTextContent("CANCELLED"));
    expect(callsTo("POST /api/tasks/1/cancel")).toHaveLength(1);
    expect(within(panel).queryByRole("button", { name: "Cancel task" })).not.toBeInTheDocument();
    expect(within(panel).getByText("The request was cancelled before it was delegated.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("poll-state")).toHaveTextContent("up to date"));
  });
});
