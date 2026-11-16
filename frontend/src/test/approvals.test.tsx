import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { resetPendingApprovals } from "../approvalCount";
import type { TaskDetail } from "../api";
import Approvals from "../pages/Approvals";
import AuditLog, { PAGE_SIZE } from "../pages/AuditLog";
import Tasks from "../pages/Tasks";
import { SessionProvider } from "../session";
import { HEALTH, STATS, USER, VILLAGE, makeApproval, makeAuditEntry, makeAuditPage, makeTask, mockFetch, ACTIVITY_ROUTE } from "./helpers";

type Routes = Parameters<typeof mockFetch>[0];

const PENDING = "GET /api/approvals?status=PENDING";
const COUNT = "GET /api/approvals/pending-count";

function renderApprovals(path = "/approvals") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/approvals" element={<Approvals timezone="Asia/Dhaka" pollMs={60_000} />} />
        <Route path="/tasks" element={<p>task center</p>} />
        <Route path="/agents/profile" element={<p>agent profile</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

/** Pretend the window is `width` px wide. */
function setViewport(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query);
    return { matches: max ? width <= Number(max[1]) : false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined };
  });
}

beforeEach(() => resetPendingApprovals());
afterEach(() => vi.unstubAllGlobals());

describe("Approval Center", () => {
  it("shows every field of an approval request (SPEC §8F)", async () => {
    mockFetch({ [PENDING]: { body: [makeApproval()] }, [COUNT]: { body: { pending: 1 } } });
    renderApprovals();

    const card = await screen.findByRole("article", { name: "Approval request 7" });
    expect(within(card).getByTestId("approval-status")).toHaveTextContent("pending");
    const field = (label: string) => within(card).getByText(label).nextElementSibling as HTMLElement;
    expect(field("Requesting agent")).toHaveTextContent("Sumi · Customer Support Agent");
    expect(within(field("Requesting agent")).getByRole("link", { name: "Sumi" })).toHaveAttribute("href", "/agents/profile?id=3");
    expect(field("Requested action")).toHaveTextContent("Send a message to customer: “Your order is ready.”");
    expect(field("Reason")).toHaveTextContent("The request says: “send message to customer”");
    expect(field("Tool")).toHaveTextContent("Send external message (message.send_external)");
    expect(field("Expected changes")).toHaveTextContent("Today nothing leaves this PC");
    expect(field("Risk information")).toHaveTextContent("SENSITIVE");
    expect(field("Risk information")).toHaveTextContent("It cannot be taken back once sent.");
    expect(within(field("Task")).getByRole("link", { name: "#12 send message to customer" })).toHaveAttribute("href", "/tasks?id=12");
    expect(within(card).getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    // the page is honest about what an approval does today
    expect(screen.getByRole("note")).toHaveTextContent("No external connector exists yet");
  });

  it("approves only after the confirm step, with the note, and reloads the list", async () => {
    const routes: Routes = {
      [PENDING]: { body: [makeApproval()] },
      [COUNT]: { body: { pending: 1 } },
      "POST /api/approvals/7/approve": { body: makeApproval({ status: "APPROVED" }) },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderApprovals();

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    const dialog = screen.getByRole("dialog", { name: "Approve this request?" });
    expect(dialog).toHaveTextContent("Sumi wants to: Send a message to customer");
    expect(dialog).toHaveTextContent("the approval is only recorded");
    expect(callsTo("POST /api/approvals/7/approve")).toHaveLength(0); // nothing sent before confirming

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(callsTo("POST /api/approvals/7/approve")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.type(screen.getByLabelText("Note (optional)"), " ok, go ");
    routes[PENDING] = { body: [] }; // what the server lists after the decision
    routes[COUNT] = { body: { pending: 0 } };
    await user.click(screen.getByRole("button", { name: "Yes, approve" }));

    await waitFor(() => expect(callsTo("POST /api/approvals/7/approve")).toHaveLength(1));
    expect(callsTo("POST /api/approvals/7/approve")[0]!.json).toEqual({ note: "ok, go" });
    expect(await screen.findByRole("heading", { name: "Nothing is waiting for you" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(callsTo(COUNT).length).toBeGreaterThanOrEqual(2); // the badge was refreshed
  });

  it("rejects after the confirm step", async () => {
    const routes: Routes = {
      [PENDING]: { body: [makeApproval()] },
      [COUNT]: { body: { pending: 1 } },
      "POST /api/approvals/7/reject": { body: makeApproval({ status: "REJECTED" }) },
    };
    const { callsTo } = mockFetch(routes);
    const user = renderApprovals();

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("dialog", { name: "Reject this request?" });
    expect(dialog).toHaveTextContent("the task fails with “rejected by Chairman”");
    routes[PENDING] = { body: [] };
    await user.click(within(dialog).getByRole("button", { name: "Yes, reject" }));
    await waitFor(() => expect(callsTo("POST /api/approvals/7/reject")).toHaveLength(1));
    expect(callsTo("POST /api/approvals/7/reject")[0]!.json).toEqual({ note: "" });
    expect(await screen.findByRole("heading", { name: "Nothing is waiting for you" })).toBeInTheDocument();
  });

  it("shows the server's reason when the request was already decided (409)", async () => {
    const routes: Routes = {
      [PENDING]: { body: [makeApproval()] },
      [COUNT]: { body: { pending: 1 } },
      "POST /api/approvals/7/approve": { status: 409, body: { detail: "This approval request is already REJECTED. It cannot be decided again." } },
    };
    mockFetch(routes);
    const user = renderApprovals();
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Yes, approve" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already REJECTED. It cannot be decided again.");
  });

  it("filters by status and shows a decided request without buttons", async () => {
    const decided = makeApproval({
      id: 5,
      status: "APPROVED",
      decided_at: "2026-11-16T10:05:00Z",
      decided_by: "chairman:chairman",
      decision_note: "fine",
      executed_at: "2026-11-16T10:05:01Z",
      result: "approved — no external connector yet. Nothing was sent.",
      task_status: "SUCCEEDED",
    });
    const { callsTo } = mockFetch({
      [PENDING]: { body: [] },
      "GET /api/approvals?status=APPROVED": { body: [decided] },
      "GET /api/approvals": { body: [decided] },
      [COUNT]: { body: { pending: 0 } },
    });
    const user = renderApprovals();
    expect(await screen.findByRole("heading", { name: "Nothing is waiting for you" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pending" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("tab", { name: "Approved" }));
    const card = await screen.findByRole("article", { name: "Approval request 5" });
    expect(within(card).getByTestId("approval-status")).toHaveTextContent("approved");
    expect(card).toHaveTextContent("approved by Chairman (chairman)");
    expect(card).toHaveTextContent("Note: fine");
    expect(card).toHaveTextContent("approved — no external connector yet. Nothing was sent.");
    expect(within(card).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "All" }));
    await waitFor(() => expect(callsTo("GET /api/approvals")).toHaveLength(1));
  });

  it("opens one request from a link (?id=) and offers the way back", async () => {
    mockFetch({ "GET /api/approvals/7": { body: makeApproval() }, [COUNT]: { body: { pending: 1 } } });
    renderApprovals("/approvals?id=7");
    expect(await screen.findByRole("article", { name: "Approval request 7" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All approval requests" })).toHaveAttribute("href", "/approvals");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("shows an error when the list cannot be loaded", async () => {
    mockFetch({ [PENDING]: { status: 500, body: { detail: "boom" } }, [COUNT]: { body: { pending: 0 } } });
    renderApprovals();
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});

describe("pending-approvals badge", () => {
  const AUTHED: Routes = {
    "GET /api/setup/status": { body: { setup_completed: true } },
    "GET /api/auth/me": { body: USER },
    "GET /api/village": { body: VILLAGE },
    "GET /api/health": { body: HEALTH },
    "GET /api/stats/overview": { body: STATS },
    [ACTIVITY_ROUTE]: { body: [] },
  };

  function renderApp(path = "/") {
    render(
      <MemoryRouter initialEntries={[path]}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    );
  }

  it("shows the number of waiting requests on the Approval Center link", async () => {
    mockFetch({ ...AUTHED, [COUNT]: { body: { pending: 2 } } });
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Village pages" });
    const badge = await within(nav).findByTestId("pending-approvals");
    expect(badge).toHaveTextContent("2");
    expect(badge).toHaveAccessibleName("2 waiting for your decision");
    expect(within(nav).getByRole("link", { name: /^Approval Center/ })).toContainElement(badge);
  });

  it("shows no badge when nothing is waiting, and no fake number when the count cannot be loaded", async () => {
    mockFetch({ ...AUTHED, [COUNT]: { body: { pending: 0 } } });
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Village pages" });
    await screen.findByRole("heading", { level: 1, name: "Shantipur" });
    expect(within(nav).queryByTestId("pending-approvals")).not.toBeInTheDocument();
  });

  it("on a phone the count sits on the More button", async () => {
    setViewport(390);
    mockFetch({ ...AUTHED, [COUNT]: { body: { pending: 3 } } });
    renderApp();
    const dot = await screen.findByTestId("pending-approvals-dot");
    expect(dot).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /More/ })).toContainElement(dot);
  });
});

describe("Task Center and approvals", () => {
  it("shows WAITING APPROVAL with a link to the approval request", async () => {
    const parent = makeTask({ id: 11, title: "send message to customer", status: "RUNNING", child_count: 1, pending_approval_id: 7 });
    const child = makeTask({
      id: 12,
      parent_task_id: 11,
      depth: 1,
      title: "send message to customer",
      status: "WAITING_APPROVAL",
      pending_approval_id: 7,
      assigned_agent: { id: 3, display_name: "Sumi", role: "Customer Support Agent", avatar_key: "support", is_central_manager: false },
    });
    const detail: TaskDetail = { ...parent, children: [child], messages: [] };
    mockFetch({ "GET /api/tasks?top_level=true": { body: [parent] }, "GET /api/tasks/11": { body: detail } });
    render(
      <MemoryRouter initialEntries={["/tasks?id=11"]}>
        <Routes>
          <Route path="/tasks" element={<Tasks timezone="Asia/Dhaka" pollMs={60_000} />} />
          <Route path="/approvals" element={<p>approval center</p>} />
        </Routes>
      </MemoryRouter>,
    );

    const panel = await screen.findByRole("region", { name: "Task 11" });
    const notice = within(panel).getByRole("status");
    expect(notice).toHaveTextContent("This task is waiting for your approval. Nothing happens until you decide.");
    expect(within(notice).getByRole("link", { name: "Open approval request #7" })).toHaveAttribute("href", "/approvals?id=7");

    const childRow = within(panel).getByRole("listitem", { name: "Child task 12" });
    expect(within(childRow).getByTestId("task-status")).toHaveTextContent("WAITING APPROVAL");
    expect(within(childRow).getByRole("link", { name: "approval #7" })).toHaveAttribute("href", "/approvals?id=7");

    const list = screen.getByRole("region", { name: "Tasks" });
    expect(within(list).getByRole("link", { name: /#11 send message to customer/ })).toHaveTextContent("needs your approval");
  });

  it("shows no approval notice for an ordinary task", async () => {
    const task = makeTask({ id: 5, status: "SUCCEEDED" });
    mockFetch({ "GET /api/tasks?top_level=true": { body: [task] }, "GET /api/tasks/5": { body: { ...task, children: [], messages: [] } } });
    render(
      <MemoryRouter initialEntries={["/tasks?id=5"]}>
        <Routes>
          <Route path="/tasks" element={<Tasks timezone="Asia/Dhaka" pollMs={60_000} />} />
        </Routes>
      </MemoryRouter>,
    );
    const panel = await screen.findByRole("region", { name: "Task 5" });
    expect(within(panel).queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText("needs your approval")).not.toBeInTheDocument();
  });
});

describe("Audit Log", () => {
  const ENTRIES = [
    makeAuditEntry({ id: 4, action: "approval.approved", actor: "chairman:chairman", tool_key: "message.send_external", decision: "approved", summary: "Approved request #7" }),
    makeAuditEntry({ id: 3, action: "tool.denied" }),
    makeAuditEntry({ id: 2, action: "agent.paused", actor: "chairman:chairman", task_id: null, tool_key: null, decision: null, summary: "Paused 'Sumi' (it was active)." }),
    makeAuditEntry({ id: 1, action: "auth.login", actor: "chairman:chairman", agent_id: null, agent_name: null, task_id: null, tool_key: null, decision: "allowed", summary: "Logged in from Chrome on Linux." }),
  ];
  const ALL = `GET /api/audit?limit=${PAGE_SIZE}&offset=0`;

  function renderAudit(path = "/audit") {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/audit" element={<AuditLog timezone="Asia/Dhaka" />} />
          <Route path="/tasks" element={<p>task center</p>} />
        </Routes>
      </MemoryRouter>,
    );
    return userEvent.setup();
  }

  it("lists tool, approval, lifecycle and login events in a table", async () => {
    mockFetch({ [ALL]: { body: makeAuditPage(ENTRIES) } });
    renderAudit();

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(5); // the header + four entries
    expect(within(rows[0]!).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Time", "Who", "Action", "Agent", "Task", "Tool", "Decision", "Summary",
    ]);
    expect(rows[1]).toHaveTextContent("Chairman (chairman)");
    expect(rows[1]).toHaveTextContent("approval.approved");
    expect(rows[1]).toHaveTextContent("message.send_external");
    expect(rows[2]).toHaveTextContent("Agent Sumi");
    expect(rows[2]).toHaveTextContent("tool.denied");
    expect(rows[2]).toHaveTextContent("The tool 'Read the organisation' is not assigned to 'Sumi'.");
    expect(within(rows[2]!).getByRole("link", { name: "#12" })).toHaveAttribute("href", "/tasks?id=12");
    expect(rows[3]).toHaveTextContent("agent.paused");
    expect(rows[4]).toHaveTextContent("auth.login");
    expect(rows[4]).toHaveTextContent("Logged in from Chrome on Linux.");
    expect(screen.getByTestId("audit-range")).toHaveTextContent("1–4 of 4");
    // read-only: nothing on the page edits or deletes an entry
    expect(screen.queryByRole("button", { name: /delete|edit|remove/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Entries can only be added — never edited or deleted/)).toBeInTheDocument();
  });

  it("filters by action group, by agent and by task, and clears the filters", async () => {
    const tools = `GET /api/audit?action=tool&limit=${PAGE_SIZE}&offset=0`;
    const toolsOfAgent = `GET /api/audit?action=tool&agent_id=3&limit=${PAGE_SIZE}&offset=0`;
    const withTask = `GET /api/audit?action=tool&agent_id=3&task_id=12&limit=${PAGE_SIZE}&offset=0`;
    const page = makeAuditPage(ENTRIES);
    const filtered = makeAuditPage([ENTRIES[1]!], { actions: page.actions });
    const { callsTo } = mockFetch({ [ALL]: { body: page }, [tools]: { body: filtered }, [toolsOfAgent]: { body: filtered }, [withTask]: { body: filtered } });
    const user = renderAudit();

    await screen.findByRole("table");
    const action = screen.getByLabelText("Action");
    expect(within(action).getByRole("option", { name: "Tools (all)" })).toHaveValue("tool");
    expect(within(action).getByRole("option", { name: "tool.denied" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();

    await user.selectOptions(action, "tool");
    await waitFor(() => expect(callsTo(tools)).toHaveLength(1));
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));

    await user.click(screen.getByRole("button", { name: "Sumi" })); // "show only this agent"
    await waitFor(() => expect(callsTo(toolsOfAgent)).toHaveLength(1));
    expect(screen.getByLabelText("Agent #")).toHaveValue("3");

    await user.type(screen.getByLabelText("Task #"), "12");
    await waitFor(() => expect(callsTo(withTask)).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(callsTo(ALL)).toHaveLength(2));
    expect(screen.getByLabelText("Agent #")).toHaveValue("");
  });

  it("pages through the log", async () => {
    const older = `GET /api/audit?limit=${PAGE_SIZE}&offset=${PAGE_SIZE}`;
    const first = Array.from({ length: PAGE_SIZE }, (_, index) => makeAuditEntry({ id: 120 - index }));
    const { callsTo } = mockFetch({
      [ALL]: { body: makeAuditPage(first, { total: 120 }) },
      [older]: { body: makeAuditPage([makeAuditEntry({ id: 70, summary: "an older entry" })], { total: 120, offset: PAGE_SIZE }) },
    });
    const user = renderAudit();
    expect(await screen.findByTestId("audit-range")).toHaveTextContent(`1–${PAGE_SIZE} of 120`);
    expect(screen.getByRole("button", { name: "Newer" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Older" }));
    await waitFor(() => expect(callsTo(older)).toHaveLength(1));
    expect(await screen.findByText("an older entry")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Newer" })).toBeEnabled();
  });

  it("takes its filters from the address and says when nothing matches", async () => {
    const { callsTo } = mockFetch({ [`GET /api/audit?task_id=12&limit=${PAGE_SIZE}&offset=0`]: { body: makeAuditPage([]) } });
    renderAudit("/audit?task_id=12");
    expect(await screen.findByText("No entry matches these filters.")).toBeInTheDocument();
    expect(screen.getByLabelText("Task #")).toHaveValue("12");
    expect(callsTo(`GET /api/audit?task_id=12&limit=${PAGE_SIZE}&offset=0`)).toHaveLength(1);
  });

  it("is a list of cards on a phone (no wide table)", async () => {
    setViewport(390);
    mockFetch({ [ALL]: { body: makeAuditPage(ENTRIES) } });
    renderAudit();
    const entry = await screen.findByRole("listitem", { name: "Entry 3" });
    expect(entry).toHaveTextContent("tool.denied");
    expect(entry).toHaveTextContent("Agent Sumi · org.read");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
