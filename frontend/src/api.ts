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
  /** The most Wards one Union may hold (backend MAX_WARDS_PER_UNION). */
  max_wards_per_union: number;
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
  /** The most ward names a template may hold (backend MAX_WARDS_PER_UNION). */
  max_wards: number;
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
  /** Every agent, the Central Manager included. */
  agents: number;
  active_agents: number;
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

// ---- devices & sessions (DEV-APP-01) ----

export interface DeviceSession {
  id: number;
  /** "Chrome on Android"; "Unknown device" when it could not be recognised. */
  device: string;
  created_at: string;
  last_seen_at: string | null;
  expires_at: string;
  /** The session this browser is using. */
  current: boolean;
}

// ---- agents (M3) ----

export type Lifecycle = "active" | "paused" | "disabled";
export type RuntimeState = "idle" | "working" | "waiting" | "offline";

export interface AgentTemplate {
  id: number;
  key: string;
  name: string;
  role: string;
  description: string;
  avatar_key: string;
  default_instructions: string;
  default_tools: string[];
  default_permissions: string[];
}

export interface CatalogItem {
  key: string;
  label: string;
  description: string;
  /** A tool that always needs the Chairman's approval, or the permission such a tool requires. */
  sensitive: boolean;
  // tools only (from the central registry):
  risk?: "READ" | "WRITE" | "SENSITIVE" | null;
  /** false = registered, but it answers "not available yet". */
  available?: boolean;
  planned_for?: string;
  required_permission?: string | null;
}

export interface AgentOptions {
  tools: CatalogItem[];
  permissions: CatalogItem[];
  providers: string[];
  /** True since M4: every tool call is checked against the agent's tools and permissions. */
  enforced: boolean;
}

export interface AgentLocation {
  office: { id: number; name: string; kind: string };
  ward: { id: number; number: number; name: string } | null;
  union: { id: number; name: string } | null;
  upazila: { id: number; name: string } | null;
  /** "Study Upazila › Academic Management › Ward 1: Class Routine" */
  path: string;
}

export interface Agent {
  id: number;
  display_name: string;
  avatar_key: string;
  role: string;
  description: string;
  template_id: number | null;
  template_key: string | null;
  template_name: string | null;
  office_id: number | null;
  /** null = the agent's office was deleted. */
  location: AgentLocation | null;
  system_instructions: string;
  allowed_tools: string[];
  permissions: string[];
  provider: string;
  lifecycle: Lifecycle;
  runtime_state: RuntimeState;
  is_central_manager: boolean;
  /** True = it has tasks or messages, so it can only be disabled, not deleted. */
  has_history: boolean;
  created_at: string;
  updated_at: string;
  disabled_at: string | null;
}

export interface AgentInput {
  template_id: number;
  display_name: string;
  office_id: number;
  role?: string;
  description?: string;
  system_instructions?: string;
  allowed_tools?: string[];
  permissions?: string[];
  activate?: boolean;
}

export type AgentPatch = Partial<Omit<AgentInput, "template_id" | "activate">>;
export type AgentAction = "activate" | "pause" | "disable";

// ---- tasks (M3) ----

export type TaskStatus = "QUEUED" | "ASSIGNED" | "RUNNING" | "WAITING_APPROVAL" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type TaskPriority = "low" | "normal" | "high";

export interface AgentRef {
  id: number;
  display_name: string;
  role: string;
  avatar_key: string;
  is_central_manager: boolean;
}

export interface Task {
  id: number;
  title: string;
  description: string;
  created_by: string;
  created_by_name: string;
  assigned_agent: AgentRef | null;
  parent_task_id: number | null;
  depth: number;
  priority: TaskPriority;
  input: Record<string, unknown>;
  output: string | null;
  status: TaskStatus;
  child_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

/** What the Central Manager decided; stored with the delegation. */
export interface Routing {
  upazila_name?: string;
  matched_keywords?: string[];
  agent_id?: number;
  agent_name?: string;
  agent_role?: string;
  agent_path?: string;
  agent_matched_words?: string[];
  active_candidates?: number;
  method?: string;
}

export interface AgentMessage {
  id: number;
  sender: AgentRef | null;
  receiver: AgentRef | null;
  task_id: number;
  type: "delegation" | "result" | "info_request";
  payload: { routing?: Routing; status?: TaskStatus; output?: string | null; error?: string | null; [key: string]: unknown };
  created_at: string;
}

export interface TaskDetail extends Task {
  children: Task[];
  /** Messages of this task and of every task below it, oldest first. */
  messages: AgentMessage[];
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`);
  return parts.length ? `?${parts.join("&")}` : "";
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

async function request<T>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
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

  // devices & sessions
  sessions: () => request<DeviceSession[]>("GET", "/api/auth/sessions"),
  revokeSession: (id: number) => request<{ revoked: number }>("POST", `/api/auth/sessions/${id}/revoke`),
  revokeOtherSessions: () => request<{ revoked: number }>("POST", "/api/auth/sessions/revoke-others"),

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
  replaceWardTemplates: (key: string, wards: { name: string; responsibility: string }[]) =>
    request<Template>("PUT", `/api/templates/${encodeURIComponent(key)}/wards`, { wards }),
  updateWardTemplate: (id: number, patch: { name?: string; responsibility?: string }) =>
    request<WardTemplate>("PATCH", `/api/templates/wards/${id}`, patch),

  // agents
  agentTemplates: () => request<AgentTemplate[]>("GET", "/api/agent-templates"),
  agentOptions: () => request<AgentOptions>("GET", "/api/agent-options"),
  agents: (filter: { upazila_id?: number | null; office_id?: number | null; lifecycle?: Lifecycle | null } = {}) =>
    request<Agent[]>("GET", `/api/agents${query(filter)}`),
  agent: (id: number) => request<Agent>("GET", `/api/agents/${id}`),
  createAgent: (input: AgentInput) => request<Agent>("POST", "/api/agents", input),
  updateAgent: (id: number, patch: AgentPatch) => request<Agent>("PATCH", `/api/agents/${id}`, patch),
  agentAction: (id: number, action: AgentAction) => request<Agent>("POST", `/api/agents/${id}/${action}`),
  deleteAgent: (id: number, confirmName: string) =>
    request<{ deleted: boolean }>("DELETE", `/api/agents/${id}`, { confirm_name: confirmName }),

  // tasks
  tasks: (filter: { status?: TaskStatus | null; agent_id?: number | null; top_level?: boolean; limit?: number } = {}) =>
    request<Task[]>("GET", `/api/tasks${query(filter)}`),
  task: (id: number) => request<TaskDetail>("GET", `/api/tasks/${id}`),
  createTask: (input: { title: string; description: string; priority: TaskPriority }) =>
    request<Task>("POST", "/api/tasks", input),
  cancelTask: (id: number) => request<TaskDetail>("POST", `/api/tasks/${id}/cancel`),
};

/** A message fit for the user from anything a failed call can throw. */
export function errorMessage(cause: unknown, fallback = "Something went wrong."): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
