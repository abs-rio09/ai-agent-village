import { vi } from "vitest";

import type { Health, User, Village } from "../api";

interface MockReply {
  status?: number;
  body: unknown;
}
type MockRoute = MockReply | ((init: RequestInit | undefined) => MockReply);

export interface RecordedCall {
  key: string;
  init: RequestInit | undefined;
  json: unknown;
}

/**
 * Replace global fetch. Routes are keyed by "METHOD /path". An unexpected request
 * throws, so a test can never silently hit an endpoint it did not declare.
 */
export function mockFetch(routes: Record<string, MockRoute>) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    if (route === undefined) {
      throw new Error(`Unexpected fetch: ${key}`);
    }
    calls.push({ key, init, json: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
    const reply = typeof route === "function" ? route(init) : route;
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls, callsTo: (key: string) => calls.filter((call) => call.key === key) };
}

export const VILLAGE: Village = {
  id: 1,
  name: "Shantipur",
  chairman_name: "Riyan",
  timezone: "Asia/Dhaka",
  ai_mode: "demo",
  ollama_url: null,
  default_structure: "standard",
  created_at: "2026-11-11T20:00:00Z",
  anthropic_key_configured: false,
};

export const USER: User = { username: "chairman", last_login_at: "2026-11-11T20:00:00Z" };

export const HEALTH: Health = {
  status: "ok",
  version: "9.9.9-test",
  db_ok: true,
  journal_mode: "wal",
  demo_mode: true,
  setup_completed: true,
};
