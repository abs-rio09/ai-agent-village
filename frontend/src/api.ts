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

// ---- organization (M2) ----

export interface Office {
  id: number;
  kind: "ward" | "central";
  ward_id: number | null;
  name: string;
  description: string;
}

export interface UpazilaCounts {
  unions: number;
  wards: number;
  /** Ward offices only — the Central Administration office is listed separately. */
  offices: number;
}

export interface UnionCounts {
  wards: number;
  offices: number;
}

export interface TreeWard {
  id: number;
  number: number;
  name: string;
  responsibility: string;
  office: Office | null;
}

export interface TreeUnion {
  id: number;
  name: string;
  description: string;
  counts: UnionCounts;
  wards: TreeWard[];
}

export interface TreeUpazila {
  id: number;
  name: string;
  description: string;
  icon: string;
  template_key: string | null;
  counts: UpazilaCounts;
  unions: TreeUnion[];
}

export interface OrgTree {
  village: { id: number; name: string };
  central_office: Office | null;
  counts: UpazilaCounts;
  upazila_count: number;
  upazilas: TreeUpazila[];
}

export interface UnionTemplate {
  id: number;
  name: string;
  sort_order: number;
}

export interface WardTemplate {
  id: number;
  number: number;
  name: string;
  responsibility: string;
}

export interface Template {
  key: string;
  name: string;
  description: string;
  icon: string;
  sort_order: number;
  unions: UnionTemplate[];
  wards: WardTemplate[];
}

export interface GenerateResult {
  unions_created: number;
  wards_created: number;
  offices_created: number;
  /** Template Unions that already exist in the Upazila and are left untouched. */
  skipped: number;
}

export interface StandardUpazilasResult {
  created: Array<{ id: number; name: string }>;
  skipped: string[];
}

export interface OverviewStats {
  upazilas: number;
  unions: number;
  wards: number;
  /** Every office, including Central Administration. */
  offices: number;
  ward_offices: number;
}

export interface UpazilaInput {
  name: string;
  description: string;
  icon: string;
  template_key: string | null;
}

export interface DeleteResult {
  deleted: boolean;
  upazilas: number;
  unions: number;
  wards: number;
  offices: number;
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

async function request<T>(method: "GET" | "POST" | "PATCH" | "DELETE", path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
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

  // organization
  orgTree: () => request<OrgTree>("GET", "/api/org/tree"),
  statsOverview: () => request<OverviewStats>("GET", "/api/stats/overview"),
  createUpazila: (input: UpazilaInput) => request<unknown>("POST", "/api/upazilas", input),
  updateUpazila: (id: number, patch: Partial<UpazilaInput>) => request<unknown>("PATCH", `/api/upazilas/${id}`, patch),
  deleteUpazila: (id: number, confirmName: string) =>
    request<DeleteResult>("DELETE", `/api/upazilas/${id}`, { confirm_name: confirmName }),
  createStandardUpazilas: () => request<StandardUpazilasResult>("POST", "/api/upazilas/standard"),
  previewStandardStructure: (id: number) =>
    request<GenerateResult>("GET", `/api/upazilas/${id}/generate-standard/preview`),
  generateStandardStructure: (id: number) => request<GenerateResult>("POST", `/api/upazilas/${id}/generate-standard`),
  createUnion: (upazilaId: number, input: { name: string; description: string }) =>
    request<unknown>("POST", `/api/upazilas/${upazilaId}/unions`, input),
  updateUnion: (id: number, patch: { name?: string; description?: string }) =>
    request<unknown>("PATCH", `/api/unions/${id}`, patch),
  deleteUnion: (id: number, confirmName: string) =>
    request<DeleteResult>("DELETE", `/api/unions/${id}`, { confirm_name: confirmName }),
  createWard: (unionId: number) => request<TreeWard>("POST", `/api/unions/${unionId}/wards`, {}),
  updateWard: (id: number, patch: { name?: string; responsibility?: string }) =>
    request<unknown>("PATCH", `/api/wards/${id}`, patch),
  deleteWard: (id: number, confirmName: string) =>
    request<DeleteResult>("DELETE", `/api/wards/${id}`, { confirm_name: confirmName }),
  updateOffice: (id: number, patch: { name?: string; description?: string }) =>
    request<Office>("PATCH", `/api/offices/${id}`, patch),

  // templates (edits affect future generation only)
  templates: () => request<Template[]>("GET", "/api/templates"),
  updateTemplate: (key: string, patch: { name?: string; description?: string }) =>
    request<Template>("PATCH", `/api/templates/${encodeURIComponent(key)}`, patch),
  updateUnionTemplate: (id: number, name: string) =>
    request<UnionTemplate>("PATCH", `/api/templates/unions/${id}`, { name }),
  updateWardTemplate: (id: number, patch: { name?: string; responsibility?: string }) =>
    request<WardTemplate>("PATCH", `/api/templates/wards/${id}`, patch),
};

/** A message fit for the user from anything a failed call can throw. */
export function errorMessage(cause: unknown, fallback = "Something went wrong."): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
