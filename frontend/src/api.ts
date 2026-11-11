// Small typed API client. Every request sends the session cookie; a 401 from any
// protected endpoint notifies the session layer, which sends the user to /login.

export type AiMode = "demo" | "ollama" | "anthropic";
export type DefaultStructure = "empty" | "standard";

export interface Health {
  status: "ok" | "degraded";
  version: string;
  db_ok: boolean;
  journal_mode: string | null;
  demo_mode: boolean;
  setup_completed: boolean;
}

export interface SetupStatus {
  setup_completed: boolean;
}

export interface User {
  username: string;
  last_login_at: string | null;
}

export interface Village {
  id: number;
  name: string;
  chairman_name: string;
  timezone: string;
  ai_mode: AiMode;
  ollama_url: string | null;
  default_structure: DefaultStructure;
  created_at: string;
  anthropic_key_configured: boolean;
}

export interface SetupPayload {
  village_name: string;
  chairman_name: string;
  username: string;
  password: string;
  timezone: string;
  ai_mode: AiMode;
  ollama_url: string | null;
  anthropic_api_key: string | null;
  default_structure: DefaultStructure;
}

export interface SetupResult {
  setup_completed: boolean;
  username: string;
  village: Village;
  anthropic_api_key: "saved, not tested" | "not provided";
}

export class ApiError extends Error {
  readonly status: number;
  /** Server-side validation messages keyed by field name (e.g. "password"). */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

let unauthorizedHandler: (() => void) | null = null;

/** Registered by the session layer: called whenever a protected call returns 401. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

interface ValidationItem {
  loc?: unknown[];
  msg?: string;
}

function parseError(status: number, data: unknown): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") {
    return new ApiError(status, detail);
  }
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    const messages: string[] = [];
    for (const item of detail as ValidationItem[]) {
      const message = (item.msg ?? "Invalid value").replace(/^Value error, /, "");
      const field = item.loc?.[item.loc.length - 1];
      if (typeof field === "string" && field !== "body") {
        fieldErrors[field] ??= message;
        messages.push(`${field}: ${message}`);
      } else {
        messages.push(message);
      }
    }
    return new ApiError(status, messages.join("; ") || "The server rejected the request.", fieldErrors);
  }
  return new ApiError(status, `Request failed (HTTP ${status}).`);
}

interface RequestOptions {
  /** Login failures are 401 too, but must not trigger the "session expired" redirect. */
  skipUnauthorizedHandler?: boolean;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Village server. Is it running? (./village status)");
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.skipUnauthorizedHandler) {
      unauthorizedHandler?.();
    }
    throw parseError(response.status, data);
  }
  return data as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  setupStatus: () => request<SetupStatus>("GET", "/api/setup/status"),
  setup: (payload: SetupPayload) => request<SetupResult>("POST", "/api/setup", payload),
  login: (username: string, password: string) =>
    request<User>("POST", "/api/auth/login", { username, password }, { skipUnauthorizedHandler: true }),
  logout: () => request<{ ok: boolean }>("POST", "/api/auth/logout"),
  me: () => request<User>("GET", "/api/auth/me"),
  village: () => request<Village>("GET", "/api/village"),
};
