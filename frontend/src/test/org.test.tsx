import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import App from "../App";
import type { TreeUpazila } from "../api";
import { SessionProvider } from "../session";
import {
  GARDEN,
  HEALTH,
  STATS,
  STUDY_EMPTY,
  STUDY_FULL,
  STUDY_UNIONS,
  STUDY_WARDS,
  TEMPLATES,
  USER,
  VILLAGE,
  makeTree,
  mockFetch,
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

/** The shell's own requests plus the tree and templates for the given Upazilas. */
function orgRoutes(upazilas: TreeUpazila[]) {
  return {
    "GET /api/setup/status": { body: { setup_completed: true } },
    "GET /api/auth/me": { body: USER },
    "GET /api/village": { body: VILLAGE },
    "GET /api/health": { body: HEALTH },
    "GET /api/stats/overview": { body: STATS },
    "GET /api/org/tree": { body: makeTree(upazilas) },
    "GET /api/templates": { body: TEMPLATES },
  };
}

const main = () => screen.getByRole("main");

describe("Upazila Management", () => {
  it("validates the create form before calling the server, then posts the trimmed name", async () => {
    const { callsTo } = mockFetch({ ...orgRoutes([]), "POST /api/upazilas": { status: 201, body: { id: 3 } } });
    const user = renderApp("/upazilas");

    await user.click(await screen.findByRole("button", { name: "New Upazila" }));
    const dialog = screen.getByRole("dialog", { name: "New Upazila" });
    // rendered on <body>, not inside the animated page: otherwise its backdrop cannot cover the window
    expect(main()).not.toContainElement(dialog);
    expect(dialog.closest("body > div")).toHaveClass("fixed", "inset-0");
    const name = within(dialog).getByLabelText("Name");
    expect(name).toHaveFocus();

    await user.click(within(dialog).getByRole("button", { name: "Create Upazila" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Enter a name.");

    await user.type(name, "   ");
    await user.click(within(dialog).getByRole("button", { name: "Create Upazila" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Enter a name.");

    await user.clear(name);
    await user.click(name);
    await user.paste("x".repeat(81));
    await user.click(within(dialog).getByRole("button", { name: "Create Upazila" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Use 80 characters or fewer.");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(callsTo("POST /api/upazilas")).toHaveLength(0); // nothing reached the server

    await user.clear(name);
    await user.type(name, "  Garden  ");
    await user.type(within(dialog).getByLabelText("Description"), "Plants");
    await user.selectOptions(within(dialog).getByLabelText("Template"), "Study Upazila");
    await user.click(within(dialog).getByRole("button", { name: "Create Upazila" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("POST /api/upazilas")).toHaveLength(1);
    expect(callsTo("POST /api/upazilas")[0]!.json).toEqual({
      name: "Garden",
      description: "Plants",
      icon: "graduation-cap", // taken from the chosen template
      template_key: "study",
    });
    expect(callsTo("GET /api/org/tree")).toHaveLength(2); // reloaded after the change
  });

  it("shows the server's error (duplicate name) and keeps the dialog open", async () => {
    mockFetch({
      ...orgRoutes([GARDEN]),
      "POST /api/upazilas": { status: 409, body: { detail: "An Upazila named 'Garden' already exists" } },
    });
    const user = renderApp("/upazilas");

    await user.click(await screen.findByRole("button", { name: "New Upazila" }));
    const dialog = screen.getByRole("dialog", { name: "New Upazila" });
    await user.type(within(dialog).getByLabelText("Name"), "Garden");
    await user.click(within(dialog).getByRole("button", { name: "Create Upazila" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("An Upazila named 'Garden' already exists");
    expect(within(dialog).getByRole("button", { name: "Create Upazila" })).toBeEnabled();
  });

  it("offers the standard Upazilas only while none exist, with the count taken from the templates", async () => {
    let created = false;
    const { callsTo } = mockFetch({
      ...orgRoutes([]),
      "GET /api/org/tree": () => ({ body: makeTree(created ? [STUDY_EMPTY, GARDEN] : []) }),
      "POST /api/upazilas/standard": () => {
        created = true;
        return { body: { created: [{ id: 1, name: "Study Upazila" }], skipped: [] } };
      },
    });
    const user = renderApp("/upazilas");

    expect(await screen.findByRole("heading", { name: "No Upazilas yet" })).toBeInTheDocument();
    // two templates in the mock → "2", not a hardcoded 6
    await user.click(await screen.findByRole("button", { name: "Create the 2 standard Upazilas" }));

    expect(await screen.findByRole("article", { name: "Study Upazila" })).toBeInTheDocument();
    expect(callsTo("POST /api/upazilas/standard")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /standard Upazilas/ })).not.toBeInTheDocument();
  });

  it("shows cards with counts, and Generate only on Upazilas that have a template", async () => {
    mockFetch(orgRoutes([STUDY_FULL, GARDEN]));
    renderApp("/upazilas");

    const study = await screen.findByRole("article", { name: "Study Upazila" });
    expect(within(study).getByText("Template: Study Upazila")).toBeInTheDocument();
    const counts = within(study).getAllByRole("definition").map((node) => node.textContent);
    expect(counts).toEqual(["5", "45", "45"]);
    expect(within(study).getByRole("button", { name: "Generate Standard Structure" })).toBeInTheDocument();

    const garden = screen.getByRole("article", { name: "Garden" });
    expect(within(garden).getByText("Custom Upazila")).toBeInTheDocument();
    expect(within(garden).getByText("Plants and trees")).toBeInTheDocument();
    expect(within(garden).queryByRole("button", { name: "Generate Standard Structure" })).not.toBeInTheDocument();
  });

  it("generate: shows the preview counts, writes only after Confirm, then shows the result", async () => {
    let generated = false;
    const { callsTo } = mockFetch({
      ...orgRoutes([STUDY_EMPTY]),
      "GET /api/org/tree": () => ({ body: makeTree([generated ? STUDY_FULL : STUDY_EMPTY]) }),
      "GET /api/upazilas/1/generate-standard/preview": {
        body: { unions_created: 5, wards_created: 45, offices_created: 45, skipped: 0 },
      },
      "POST /api/upazilas/1/generate-standard": () => {
        generated = true;
        return { body: { unions_created: 4, wards_created: 36, offices_created: 36, skipped: 1 } };
      },
    });
    const user = renderApp("/upazilas");

    const card = await screen.findByRole("article", { name: "Study Upazila" });
    await user.click(within(card).getByRole("button", { name: "Generate Standard Structure" }));
    const dialog = screen.getByRole("dialog", { name: "Generate Standard Structure" });

    expect(await within(dialog).findByRole("heading", { name: "This will create" })).toBeInTheDocument();
    expect(within(dialog).getByTestId("preview-unions")).toHaveTextContent("5");
    expect(within(dialog).getByTestId("preview-wards")).toHaveTextContent("45");
    expect(within(dialog).getByTestId("preview-offices")).toHaveTextContent("45");
    expect(callsTo("POST /api/upazilas/1/generate-standard")).toHaveLength(0); // preview only

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    // the result shows what the server REALLY created, not the preview numbers
    expect(await within(dialog).findByRole("heading", { name: "Created" })).toBeInTheDocument();
    expect(within(dialog).getByTestId("result-unions")).toHaveTextContent("4");
    expect(within(dialog).getByTestId("result-wards")).toHaveTextContent("36");
    expect(within(dialog).getByTestId("result-offices")).toHaveTextContent("36");
    expect(within(dialog).getByText(/1 template Union already exists/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(callsTo("POST /api/upazilas/1/generate-standard")).toHaveLength(1);

    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const counts = within(screen.getByRole("article", { name: "Study Upazila" })).getAllByRole("definition");
    expect(counts.map((node) => node.textContent)).toEqual(["5", "45", "45"]); // cards were reloaded
  });

  it("generate: offers no Confirm when everything already exists, and shows a failed preview", async () => {
    mockFetch({
      ...orgRoutes([STUDY_FULL, { ...STUDY_EMPTY, id: 7, name: "Broken" }]),
      "GET /api/upazilas/1/generate-standard/preview": {
        body: { unions_created: 0, wards_created: 0, offices_created: 0, skipped: 5 },
      },
      "GET /api/upazilas/7/generate-standard/preview": { status: 400, body: { detail: "This Upazila has no template" } },
    });
    const user = renderApp("/upazilas");

    const card = await screen.findByRole("article", { name: "Study Upazila" });
    await user.click(within(card).getByRole("button", { name: "Generate Standard Structure" }));
    let dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("heading", { name: "Nothing to create" })).toBeInTheDocument();
    expect(within(dialog).getByText(/5 template Unions already exist/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));

    await user.click(within(screen.getByRole("article", { name: "Broken" })).getByRole("button", { name: "Generate Standard Structure" }));
    dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This Upazila has no template");
    expect(within(dialog).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  });

  it("delete is blocked until the typed name matches exactly", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([STUDY_FULL]),
      "DELETE /api/upazilas/1": { body: { deleted: true, upazilas: 1, unions: 5, wards: 45, offices: 45 } },
    });
    const user = renderApp("/upazilas");

    await user.click(await screen.findByRole("button", { name: "Delete Study Upazila" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Upazila" });
    expect(dialog).toHaveTextContent("5 Unions, 45 Wards and 45 Offices"); // what goes with it
    const confirm = within(dialog).getByRole("button", { name: "Delete Upazila" });
    const input = within(dialog).getByLabelText(/Type the name to confirm/);
    expect(confirm).toBeDisabled();

    await user.type(input, "Study");
    expect(confirm).toBeDisabled();
    await user.type(input, " upazila"); // wrong case
    expect(confirm).toBeDisabled();
    await user.keyboard("{Enter}"); // submitting the form by keyboard is blocked too
    expect(callsTo("DELETE /api/upazilas/1")).toHaveLength(0);

    await user.clear(input);
    await user.type(input, "Study Upazila");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("DELETE /api/upazilas/1")).toHaveLength(1);
    expect(callsTo("DELETE /api/upazilas/1")[0]!.json).toEqual({ confirm_name: "Study Upazila" });
  });

  it("shows the server's error when a delete fails", async () => {
    mockFetch({ ...orgRoutes([GARDEN]), "DELETE /api/upazilas/2": { status: 409, body: { detail: "Agents still work here" } } });
    const user = renderApp("/upazilas");

    await user.click(await screen.findByRole("button", { name: "Delete Garden" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Upazila" });
    await user.type(within(dialog).getByLabelText(/Type the name to confirm/), "Garden");
    await user.click(within(dialog).getByRole("button", { name: "Delete Upazila" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Agents still work here");
    expect(screen.getByRole("article", { name: "Garden" })).toBeInTheDocument();
  });

  it("shows a clear error when the organization cannot be loaded", async () => {
    mockFetch({ ...orgRoutes([]), "GET /api/org/tree": { status: 500, body: { detail: "database is locked" } } });
    renderApp("/upazilas");
    expect(await within(await screen.findByRole("main")).findByRole("alert")).toHaveTextContent("database is locked");
  });
});

describe("tree view and breadcrumbs", () => {
  it("expands an Upazila to its Unions and a Union to its Wards", async () => {
    mockFetch(orgRoutes([STUDY_FULL, GARDEN]));
    const user = renderApp("/upazilas?tab=tree");

    const tree = await screen.findByRole("region", { name: "Organization tree" });
    expect(within(tree).getByText("Shantipur")).toBeInTheDocument();
    expect(within(tree).getByText("Central Administration")).toBeInTheDocument();
    expect(within(tree).getByRole("link", { name: "Study Upazila" })).toHaveAttribute("href", "/unions?upazila=1");
    expect(within(tree).getByText("2 Upazilas · 5 Unions · 45 Wards · 45 ward Offices")).toBeInTheDocument();
    expect(within(tree).queryByText("Academic Management")).not.toBeInTheDocument(); // collapsed

    const upazilaToggle = within(tree).getByRole("button", { name: "Expand Study Upazila" });
    expect(upazilaToggle).toHaveAttribute("aria-expanded", "false");
    await user.click(upazilaToggle);
    expect(within(tree).getByRole("button", { name: "Collapse Study Upazila" })).toHaveAttribute("aria-expanded", "true");
    for (const union of STUDY_UNIONS) {
      expect(within(tree).getByRole("link", { name: union })).toBeInTheDocument();
    }
    expect(within(tree).queryByText("Class Routine")).not.toBeInTheDocument(); // wards still collapsed

    await user.click(within(tree).getByRole("button", { name: "Expand Academic Management" }));
    for (const ward of STUDY_WARDS.filter((name) => name !== "Exam Preparation")) {
      expect(within(tree).getByRole("link", { name: ward })).toBeInTheDocument();
    }
    expect(within(tree).getByRole("link", { name: "Class Routine" })).toHaveAttribute("href", "/wards?union=11&ward=111");
    expect(within(tree).getByText("— Class Routine Office")).toBeInTheDocument();
    expect(within(tree).getAllByText(/^Ward \d$/)).toHaveLength(9);

    await user.click(within(tree).getByRole("button", { name: "Expand Garden" }));
    expect(within(tree).getByText("No Unions yet.")).toBeInTheDocument();

    await user.click(within(tree).getByRole("button", { name: "Collapse Study Upazila" }));
    expect(within(tree).queryByText("Academic Management")).not.toBeInTheDocument();

    await user.click(within(tree).getByRole("button", { name: "Expand all" }));
    expect(within(tree).getAllByText(/^Ward \d$/)).toHaveLength(45);
    await user.click(within(tree).getByRole("button", { name: "Collapse all" }));
    expect(within(tree).queryByText("Academic Management")).not.toBeInTheDocument();
  });

  it("shows Village › Upazila › Union › Ward and navigates back up", async () => {
    mockFetch(orgRoutes([STUDY_FULL, GARDEN]));
    const user = renderApp("/wards?union=12&ward=123");

    const crumbs = await screen.findByRole("navigation", { name: "Breadcrumb" });
    await waitFor(() =>
      expect(within(crumbs).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
        "Shantipur",
        "Study Upazila",
        "Course Learning",
        "Ward 3: Exam Preparation",
      ]),
    );
    expect(within(crumbs).getByText("Ward 3: Exam Preparation")).toHaveAttribute("aria-current", "page");

    await user.click(within(crumbs).getByRole("link", { name: "Study Upazila" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Union Management" })).toBeInTheDocument();
    const unionCrumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(unionCrumbs).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Shantipur", "Study Upazila"]);

    await user.click(within(unionCrumbs).getByRole("link", { name: "Shantipur" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Upazila Management" })).toBeInTheDocument();
  });
});

describe("Union Management", () => {
  it("lists the Unions of the picked Upazila and creates a new one", async () => {
    const { callsTo } = mockFetch({ ...orgRoutes([STUDY_FULL, GARDEN]), "POST /api/upazilas/2/unions": { status: 201, body: {} } });
    const user = renderApp("/unions");

    const list = await screen.findByRole("list", { name: "Unions of Study Upazila" });
    expect(within(list).getAllByRole("heading").map((node) => node.textContent)).toEqual(STUDY_UNIONS);
    expect(within(list).getAllByText("9 wards · 9 offices")).toHaveLength(5);
    expect(within(list).getByRole("link", { name: "Wards of Course Learning" })).toHaveAttribute("href", "/wards?union=12");

    await user.selectOptions(screen.getByLabelText("Upazila"), "Garden");
    expect(await screen.findByRole("heading", { name: "Garden has no Unions yet" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New Union" }));
    const dialog = screen.getByRole("dialog", { name: "New Union in Garden" });
    await user.click(within(dialog).getByRole("button", { name: "Create Union" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Enter a name.");
    await user.type(within(dialog).getByLabelText("Name"), " North ");
    await user.click(within(dialog).getByRole("button", { name: "Create Union" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("POST /api/upazilas/2/unions")[0]!.json).toEqual({ name: "North", description: "" });
  });

  it("edits and deletes a Union (delete needs the typed name)", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([STUDY_FULL]),
      "PATCH /api/unions/11": { body: {} },
      "DELETE /api/unions/11": { body: { deleted: true, upazilas: 0, unions: 1, wards: 9, offices: 9 } },
    });
    const user = renderApp("/unions?upazila=1");

    await user.click(await screen.findByRole("button", { name: "Edit Academic Management" }));
    const edit = screen.getByRole("dialog", { name: "Edit Union" });
    const name = within(edit).getByLabelText("Name");
    expect(name).toHaveValue("Academic Management");
    await user.clear(name);
    await user.type(name, "Campus");
    await user.click(within(edit).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("PATCH /api/unions/11")[0]!.json).toEqual({ name: "Campus", description: "" });

    await user.click(screen.getByRole("button", { name: "Delete Academic Management" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Union" });
    expect(dialog).toHaveTextContent("9 Wards and 9 Offices");
    expect(within(dialog).getByRole("button", { name: "Delete Union" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Type the name to confirm/), "Academic Management");
    await user.click(within(dialog).getByRole("button", { name: "Delete Union" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("DELETE /api/unions/11")[0]!.json).toEqual({ confirm_name: "Academic Management" });
  });

  it("points to Upazila Management when there are no Upazilas", async () => {
    mockFetch(orgRoutes([]));
    renderApp("/unions");
    expect(await screen.findByRole("heading", { name: "No Upazilas yet" })).toBeInTheDocument();
    expect(within(main()).getByRole("link", { name: "Go to Upazila Management" })).toHaveAttribute("href", "/upazilas");
    expect(screen.queryByRole("button", { name: "New Union" })).not.toBeInTheDocument();
  });
});

describe("Ward & Office Management", () => {
  it("shows the ward grid of the picked Union with number, name, responsibility and office", async () => {
    mockFetch(orgRoutes([STUDY_FULL]));
    const user = renderApp("/wards");

    const grid = await screen.findByRole("group", { name: "Wards of Academic Management" });
    const cards = within(grid).getAllByRole("article");
    expect(cards).toHaveLength(9);
    expect(cards[0]).toHaveAccessibleName("Ward 1: Class Routine");
    expect(within(cards[0]!).getByText("Ward 1")).toBeInTheDocument();
    expect(within(cards[0]!).getByRole("heading", { name: "Class Routine" })).toBeInTheDocument();
    expect(within(cards[0]!).getByText("Class Routine Office")).toBeInTheDocument();
    expect(cards[8]).toHaveAccessibleName("Ward 9: Daily Academic Reporting");

    await user.selectOptions(screen.getByLabelText("Union"), "Course Learning");
    expect(await screen.findByRole("group", { name: "Wards of Course Learning" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Central Administration office" })).toHaveTextContent("Central Administration");
  });

  it("edits a ward inline: only what changed is sent", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([STUDY_FULL]),
      "PATCH /api/wards/111": { body: {} },
      "PATCH /api/offices/1111": { body: {} },
    });
    const user = renderApp("/wards?union=11");

    await user.click(await screen.findByRole("button", { name: "Edit ward 1" }));
    const card = screen.getByRole("article", { name: "Ward 1: Class Routine" });
    const name = within(card).getByLabelText("Ward name");
    expect(name).toHaveValue("Class Routine");
    expect(within(card).getByLabelText("Office name")).toHaveValue("Class Routine Office");

    await user.clear(name);
    await user.click(within(card).getByRole("button", { name: "Save" }));
    expect(within(card).getByRole("alert")).toHaveTextContent("Enter a ward name.");
    expect(callsTo("PATCH /api/wards/111")).toHaveLength(0);

    await user.type(name, " Timetable ");
    await user.clear(within(card).getByLabelText("Responsibility"));
    await user.type(within(card).getByLabelText("Responsibility"), "Weekly timetable");
    await user.click(within(card).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(within(card).queryByLabelText("Ward name")).not.toBeInTheDocument());
    expect(callsTo("PATCH /api/wards/111")[0]!.json).toEqual({ name: "Timetable", responsibility: "Weekly timetable" });
    expect(callsTo("PATCH /api/offices/1111")).toHaveLength(0); // the office name was not touched

    // now only the office name
    await user.click(screen.getByRole("button", { name: "Edit ward 1" }));
    const office = within(card).getByLabelText("Office name");
    await user.clear(office);
    await user.type(office, "Front Desk");
    await user.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(callsTo("PATCH /api/offices/1111")).toHaveLength(1));
    expect(callsTo("PATCH /api/offices/1111")[0]!.json).toEqual({ name: "Front Desk" });
    expect(callsTo("PATCH /api/wards/111")).toHaveLength(1); // unchanged ward: no second call
  });

  it("adds the next ward and deletes one after the name is typed", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([STUDY_FULL]),
      "POST /api/unions/11/wards": { status: 201, body: { id: 999, number: 10, name: "Ward 10", responsibility: "", office: null } },
      "DELETE /api/wards/112": { body: { deleted: true, upazilas: 0, unions: 0, wards: 1, offices: 1 } },
    });
    const user = renderApp("/wards?union=11");

    await user.click(await screen.findByRole("button", { name: "Add ward" }));
    await waitFor(() => expect(callsTo("POST /api/unions/11/wards")).toHaveLength(1));
    await waitFor(() => expect(callsTo("GET /api/org/tree")).toHaveLength(2));

    await user.click(screen.getByRole("button", { name: "Delete ward 2" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Ward" });
    expect(dialog).toHaveTextContent("its Office “Assignment & Deadline Office”");
    const confirm = within(dialog).getByRole("button", { name: "Delete Ward" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Type the name to confirm/), "Assignment & Deadline");
    await user.click(confirm);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("DELETE /api/wards/112")[0]!.json).toEqual({ confirm_name: "Assignment & Deadline" });
  });

  it("renames the Central Administration office", async () => {
    const { callsTo } = mockFetch({ ...orgRoutes([]), "PATCH /api/offices/1": { body: {} } });
    const user = renderApp("/wards");

    await user.click(await screen.findByRole("button", { name: "Edit central office" }));
    const name = screen.getByLabelText("Central office name");
    await user.clear(name);
    await user.type(name, "Chairman's Office");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(callsTo("PATCH /api/offices/1")).toHaveLength(1));
    expect(callsTo("PATCH /api/offices/1")[0]!.json).toEqual({ name: "Chairman's Office", description: "" });
  });
});

describe("Templates", () => {
  it("saves only the template fields that changed", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([]),
      "PATCH /api/templates/unions/2": { body: {} },
      "PATCH /api/templates/wards/1": { body: {} },
    });
    const user = renderApp("/upazilas?tab=templates");

    const section = await screen.findByRole("region", { name: "Template Study Upazila" });
    expect(within(section).queryByLabelText("Template name")).not.toBeInTheDocument(); // collapsed
    await user.click(within(section).getByRole("button", { name: /Study Upazila/ }));
    expect(within(section).getByLabelText("Template name")).toHaveValue("Study Upazila");
    expect(within(section).getByLabelText("Union 2 name")).toHaveValue("Course Learning");
    expect(within(section).getByLabelText("Ward 1 name")).toHaveValue("Class Routine");
    const save = within(section).getByRole("button", { name: "Save template" });
    expect(save).toBeDisabled(); // nothing changed yet

    const union = within(section).getByLabelText("Union 2 name");
    await user.clear(union);
    await user.type(union, "Online Courses");
    const responsibility = within(section).getByLabelText("Ward 1 responsibility");
    await user.clear(responsibility);
    await user.type(responsibility, "Weekly timetable");
    await user.click(save);

    await waitFor(() => expect(callsTo("PATCH /api/templates/wards/1")).toHaveLength(1));
    expect(callsTo("PATCH /api/templates/unions/2")[0]!.json).toEqual({ name: "Online Courses" });
    expect(callsTo("PATCH /api/templates/wards/1")[0]!.json).toEqual({ name: "Class Routine", responsibility: "Weekly timetable" });
    expect(callsTo("GET /api/templates")).toHaveLength(2); // reloaded from the server
    expect(screen.getByText(/future/)).toBeInTheDocument(); // the "future generation only" note
  });

  it("refuses an empty name and shows a server error", async () => {
    const { callsTo } = mockFetch({
      ...orgRoutes([]),
      "PATCH /api/templates/business": { status: 409, body: { detail: "Another Upazila template is already named 'Study Upazila'" } },
    });
    const user = renderApp("/upazilas?tab=templates");

    const section = await screen.findByRole("region", { name: "Template Business Upazila" });
    await user.click(within(section).getByRole("button", { name: /Business Upazila/ }));
    const name = within(section).getByLabelText("Template name");
    await user.clear(name);
    await user.click(within(section).getByRole("button", { name: "Save template" }));
    expect(within(section).getByRole("alert")).toHaveTextContent("Every name must be filled in.");
    expect(callsTo("PATCH /api/templates/business")).toHaveLength(0);

    await user.type(name, "Study Upazila");
    await user.click(within(section).getByRole("button", { name: "Save template" }));
    expect(await within(section).findByRole("alert")).toHaveTextContent("already named 'Study Upazila'");
  });
});
