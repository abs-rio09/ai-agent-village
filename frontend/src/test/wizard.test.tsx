import { render, screen } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import SetupWizard, { passwordStrength } from "../pages/SetupWizard";
import { VILLAGE, mockFetch } from "./helpers";

const PASSWORD = "correct horse battery";
const API_KEY = "sk-ant-api03-TESTKEY_abcdefghijklmnopqrstuvwxyz";

const heading = (name: string) => screen.getByRole("heading", { level: 2, name });
const next = (user: UserEvent) => user.click(screen.getByRole("button", { name: "Next" }));

function renderWizard() {
  const onComplete = vi.fn();
  render(<SetupWizard onComplete={onComplete} />);
  return { onComplete, user: userEvent.setup() };
}

async function fillVillage(user: UserEvent) {
  await user.type(screen.getByLabelText("Village name"), "Shantipur");
  await user.type(screen.getByLabelText("Chairman name"), "Riyan");
  await next(user);
}

async function fillAdmin(user: UserEvent, password = PASSWORD, confirm = password) {
  await user.type(screen.getByLabelText("Username"), "Chairman");
  await user.type(screen.getByLabelText("Password"), password);
  await user.type(screen.getByLabelText("Confirm password"), confirm);
  await next(user);
}

const setupOk = {
  status: 201,
  body: { setup_completed: true, username: "chairman", village: VILLAGE, anthropic_api_key: "not provided" },
};

describe("setup wizard", () => {
  it("blocks Next on invalid input and continues once it is fixed", async () => {
    const { user } = renderWizard();
    expect(heading("Village & Chairman")).toBeInTheDocument();

    await next(user);
    expect(heading("Village & Chairman")).toBeInTheDocument();
    expect(screen.getByText("Enter a village name.")).toBeInTheDocument();
    expect(screen.getByText("Enter the chairman's name.")).toBeInTheDocument();
    expect(screen.getByLabelText("Village name")).toHaveAttribute("aria-invalid", "true");

    await user.type(screen.getByLabelText("Village name"), "   ");
    await user.type(screen.getByLabelText("Chairman name"), "Riyan");
    await next(user);
    expect(heading("Village & Chairman")).toBeInTheDocument(); // whitespace is not a name

    await user.type(screen.getByLabelText("Village name"), "Shantipur");
    await next(user);
    expect(heading("Admin account")).toBeInTheDocument();
  });

  it("rejects a short password and shows the strength hint", async () => {
    const { user } = renderWizard();
    await fillVillage(user);

    await user.type(screen.getByLabelText("Username"), "chairman");
    await user.type(screen.getByLabelText("Password"), "short");
    expect(screen.getByTestId("password-strength")).toHaveTextContent("Too short — 5 more characters needed");
    await user.type(screen.getByLabelText("Confirm password"), "short");
    await next(user);

    expect(heading("Admin account")).toBeInTheDocument();
    expect(screen.getByText("The password needs at least 10 characters.")).toBeInTheDocument();
  });

  it("shows a password mismatch error", async () => {
    const { user } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user, PASSWORD, "correct horse batterx");

    expect(heading("Admin account")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Confirm password"));
    await user.type(screen.getByLabelText("Confirm password"), PASSWORD);
    await next(user);
    expect(heading("Timezone")).toBeInTheDocument();
  });

  it("goes Back without losing what was entered", async () => {
    const { user } = renderWizard();
    await fillVillage(user);
    expect(heading("Admin account")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(heading("Village & Chairman")).toBeInTheDocument();
    expect(screen.getByLabelText("Village name")).toHaveValue("Shantipur");
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();
  });

  it("submits the correct payload in Demo Mode", async () => {
    const { calls, fetchMock } = mockFetch({ "POST /api/setup": setupOk });
    const { user, onComplete } = renderWizard();

    await fillVillage(user);
    await fillAdmin(user);

    expect(screen.getByLabelText("Timezone")).toHaveValue("Asia/Dhaka"); // default
    await next(user);

    expect(heading("AI mode")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Demo Mode/ })).toBeChecked(); // default
    await next(user);

    expect(heading("Default structure")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Empty village/ }));
    await next(user);

    expect(heading("Review & Finish")).toBeInTheDocument();
    expect(screen.queryByText(PASSWORD)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled(); // nothing is sent before Finish

    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    expect(calls).toHaveLength(1);
    expect(calls[0]!.key).toBe("POST /api/setup");
    expect(calls[0]!.init?.credentials).toBe("include");
    expect(calls[0]!.json).toEqual({
      village_name: "Shantipur",
      chairman_name: "Riyan",
      username: "chairman",
      password: PASSWORD,
      timezone: "Asia/Dhaka",
      ai_mode: "demo",
      ollama_url: null,
      anthropic_api_key: null,
      default_structure: "empty",
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("requires a localhost URL for Ollama and sends it", async () => {
    const { calls } = mockFetch({ "POST /api/setup": setupOk });
    const { user } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user);
    await next(user); // timezone

    await user.click(screen.getByRole("radio", { name: /Local AI \(Ollama\)/ }));
    const url = screen.getByLabelText("Ollama URL");
    expect(url).toHaveValue("http://127.0.0.1:11434");
    await user.clear(url);
    await user.type(url, "http://example.com:11434");
    await next(user);
    expect(heading("AI mode")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("http:// URL on this PC");

    await user.clear(url);
    await user.type(url, "http://localhost:11434");
    await next(user);
    await next(user); // default structure
    expect(screen.getByText("Ollama: not tested")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    expect(calls[0]!.json).toMatchObject({
      ai_mode: "ollama",
      ollama_url: "http://localhost:11434",
      anthropic_api_key: null,
      default_structure: "standard",
    });
  });

  it("marks the Anthropic key as saved, not tested, and never displays it", async () => {
    const { calls } = mockFetch({ "POST /api/setup": setupOk });
    const { user } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user);
    await next(user); // timezone

    await user.click(screen.getByRole("radio", { name: /Cloud AI \(Anthropic\)/ }));
    const key = screen.getByLabelText("Anthropic API key (saved, not tested)");
    expect(key).toHaveAttribute("type", "password");
    await next(user);
    expect(heading("AI mode")).toBeInTheDocument(); // a key is required for this mode

    await user.type(key, API_KEY);
    await next(user);
    await next(user); // default structure

    expect(screen.getByText("Anthropic: not tested")).toBeInTheDocument();
    expect(screen.getByText("provided (hidden) — saved, not tested")).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(API_KEY))).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    expect(calls[0]!.json).toMatchObject({ ai_mode: "anthropic", anthropic_api_key: API_KEY, ollama_url: null });
  });

  it("does not send a key that was typed before switching back to Demo Mode", async () => {
    const { calls } = mockFetch({ "POST /api/setup": setupOk });
    const { user } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user);
    await next(user);

    await user.click(screen.getByRole("radio", { name: /Cloud AI \(Anthropic\)/ }));
    await user.type(screen.getByLabelText("Anthropic API key (saved, not tested)"), API_KEY);
    await user.click(screen.getByRole("radio", { name: /Demo Mode/ }));
    await next(user);
    await next(user);
    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    expect(calls[0]!.json).toMatchObject({ ai_mode: "demo", anthropic_api_key: null });
  });

  it("shows server validation errors on the right step", async () => {
    mockFetch({
      "POST /api/setup": {
        status: 422,
        body: { detail: [{ loc: ["body", "username"], msg: "Value error, must be 3-32 characters", type: "value_error" }] },
      },
    });
    const { user, onComplete } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user);
    await next(user);
    await next(user);
    await next(user);
    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Admin account" })).toBeInTheDocument();
    expect(screen.getByText("must be 3-32 characters")).toBeInTheDocument();
    expect(screen.getByText(/The server rejected some values/)).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("shows the server message when setup was already completed", async () => {
    mockFetch({ "POST /api/setup": { status: 409, body: { detail: "Setup has already been completed" } } });
    const { user, onComplete } = renderWizard();
    await fillVillage(user);
    await fillAdmin(user);
    await next(user);
    await next(user);
    await next(user);
    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    expect(await screen.findByText("Setup has already been completed")).toBeInTheDocument();
    expect(heading("Review & Finish")).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe("passwordStrength", () => {
  it("grades passwords", () => {
    expect(passwordStrength("").score).toBe(0);
    expect(passwordStrength("123456789").score).toBe(1);
    expect(passwordStrength("abcdefghij").score).toBe(2);
    expect(passwordStrength("Abcdefghij1").score).toBe(3);
    expect(passwordStrength("correct horse battery staple").score).toBe(4);
  });
});
