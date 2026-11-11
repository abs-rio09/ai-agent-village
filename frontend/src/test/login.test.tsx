import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Login from "../pages/Login";
import { USER, mockFetch } from "./helpers";

async function submit(username: string, password: string) {
  const onLoggedIn = vi.fn();
  render(<Login onLoggedIn={onLoggedIn} />);
  const user = userEvent.setup();
  if (username) await user.type(screen.getByLabelText("Username"), username);
  if (password) await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
  return { onLoggedIn };
}

describe("login page", () => {
  it("shows the server error for a wrong password", async () => {
    const { calls } = mockFetch({
      "POST /api/auth/login": { status: 401, body: { detail: "Invalid username or password" } },
    });
    const { onLoggedIn } = await submit("chairman", "wrong password!");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(onLoggedIn).not.toHaveBeenCalled();
    expect(calls[0]!.json).toEqual({ username: "chairman", password: "wrong password!" });
    expect(calls[0]!.init?.credentials).toBe("include");
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled(); // can try again
  });

  it("shows the lockout message on 429", async () => {
    mockFetch({
      "POST /api/auth/login": {
        status: 429,
        body: { detail: "Too many failed login attempts. Try again in 5 minute(s)." },
      },
    });
    await submit("chairman", "wrong password!");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed login attempts");
  });

  it("does not call the server with empty fields", async () => {
    const { fetchMock } = mockFetch({});
    await submit("", "");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your username and password.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports success to the app", async () => {
    mockFetch({ "POST /api/auth/login": { body: USER } });
    const { onLoggedIn } = await submit("chairman", "correct horse battery");
    expect(onLoggedIn).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
