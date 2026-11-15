import { vi } from "vitest";

import type {
  Agent,
  AgentOptions,
  AgentTemplate,
  Health,
  OrgTree,
  OverviewStats,
  Task,
  TaskDetail,
  Template,
  TreeUnion,
  TreeUpazila,
  User,
  Village,
} from "../api";

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

export const STATS: OverviewStats = { upazilas: 2, unions: 5, wards: 45, offices: 46, ward_offices: 45, agents: 1, active_agents: 1 };

export const STUDY_UNIONS = [
  "Academic Management",
  "Course Learning",
  "Exam Preparation",
  "Research Paper Learning",
  "Academic Documentation",
];

export const STUDY_WARDS = [
  "Class Routine",
  "Assignment & Deadline",
  "Exam Preparation",
  "Learning Materials",
  "Note Making",
  "Course Tutor",
  "Academic Progress",
  "Study Planning",
  "Daily Academic Reporting",
];

export const TEMPLATES: Template[] = [
  {
    key: "study",
    name: "Study Upazila",
    description: "",
    icon: "graduation-cap",
    sort_order: 1,
    unions: STUDY_UNIONS.map((name, index) => ({ id: index + 1, name, sort_order: index + 1 })),
    wards: STUDY_WARDS.map((name, index) => ({ id: index + 1, number: index + 1, name, responsibility: name })),
    max_wards: 9,
  },
  {
    key: "business",
    name: "Business Upazila",
    description: "",
    icon: "store",
    sort_order: 2,
    unions: [{ id: 6, name: "Business Strategy", sort_order: 1 }],
    wards: [{ id: 10, number: 1, name: "Ward 1", responsibility: "" }],
    max_wards: 9,
  },
];

/** Union 11, 12, … with wards 111…119, 121…129, each ward with its office. */
function studyUnion(index: number, name: string): TreeUnion {
  const id = 11 + index;
  return {
    id,
    name,
    description: "",
    counts: { wards: STUDY_WARDS.length, offices: STUDY_WARDS.length },
    wards: STUDY_WARDS.map((wardName, wardIndex) => {
      const wardId = id * 10 + wardIndex + 1;
      return {
        id: wardId,
        number: wardIndex + 1,
        name: wardName,
        responsibility: wardName,
        office: { id: wardId + 1000, kind: "ward", ward_id: wardId, name: `${wardName} Office`, description: "" },
      };
    }),
  };
}

export const STUDY_EMPTY: TreeUpazila = {
  id: 1,
  name: "Study Upazila",
  description: "",
  icon: "graduation-cap",
  template_key: "study",
  counts: { unions: 0, wards: 0, offices: 0 },
  unions: [],
};

export const STUDY_FULL: TreeUpazila = {
  ...STUDY_EMPTY,
  counts: { unions: 5, wards: 45, offices: 45 },
  unions: STUDY_UNIONS.map((name, index) => studyUnion(index, name)),
};

/** STUDY_FULL, but its first Union (id 11) has only 8 wards (Ward 9 was deleted). */
export const STUDY_EIGHT_WARDS: TreeUpazila = {
  ...STUDY_FULL,
  counts: { unions: 5, wards: 44, offices: 44 },
  unions: STUDY_FULL.unions.map((union, index) =>
    index === 0 ? { ...union, counts: { wards: 8, offices: 8 }, wards: union.wards.slice(0, 8) } : union,
  ),
};

export const GARDEN: TreeUpazila = {
  id: 2,
  name: "Garden",
  description: "Plants and trees",
  icon: "",
  template_key: null,
  counts: { unions: 0, wards: 0, offices: 0 },
  unions: [],
};

export function makeTree(upazilas: TreeUpazila[]): OrgTree {
  return {
    village: { id: 1, name: "Shantipur" },
    central_office: { id: 1, kind: "central", ward_id: null, name: "Central Administration", description: "" },
    counts: {
      unions: upazilas.reduce((sum, upazila) => sum + upazila.counts.unions, 0),
      wards: upazilas.reduce((sum, upazila) => sum + upazila.counts.wards, 0),
      offices: upazilas.reduce((sum, upazila) => sum + upazila.counts.offices, 0),
    },
    upazila_count: upazilas.length,
    max_wards_per_union: 9,
    upazilas,
  };
}

// ---------------------------------------------------------------- agents + tasks (M3)

export const AGENT_TEMPLATES: AgentTemplate[] = [
  {
    id: 1,
    key: "village_manager",
    name: "Village Manager",
    role: "Village Manager",
    description: "Routes requests.",
    avatar_key: "manager",
    default_instructions: "Route every request.",
    default_tools: ["create_task"],
    default_permissions: ["delegate_tasks"],
  },
  {
    id: 4,
    key: "study_assistant",
    name: "Study Assistant",
    role: "Study Assistant",
    description: "Helps with study planning and exam preparation.",
    avatar_key: "student",
    default_instructions: "You are a study assistant.",
    default_tools: ["read_documents", "read_calendar"],
    default_permissions: ["read_upazila_memory"],
  },
];

export const AGENT_OPTIONS: AgentOptions = {
  tools: [
    { key: "read_documents", label: "Read permitted documents", description: "Read documents.", sensitive: false },
    { key: "read_calendar", label: "Read calendar", description: "Read the calendar.", sensitive: false },
    { key: "create_task", label: "Create task", description: "Create a task.", sensitive: false },
  ],
  permissions: [
    { key: "read_upazila_memory", label: "Read Upazila memory", description: "Read its Upazila's knowledge.", sensitive: false },
    { key: "delegate_tasks", label: "Delegate tasks", description: "Hand work to other agents.", sensitive: false },
    { key: "spend_money", label: "Spend money", description: "Make purchases.", sensitive: true },
  ],
  providers: ["demo"],
  enforced: false,
};

export const CENTRAL_MANAGER: Agent = {
  id: 1,
  display_name: "Central Manager",
  avatar_key: "manager",
  role: "Village Manager",
  description: "Routes requests.",
  template_id: 1,
  template_key: "village_manager",
  template_name: "Village Manager",
  office_id: 1,
  location: { office: { id: 1, name: "Central Administration", kind: "central" }, ward: null, union: null, upazila: null, path: "Central Administration" },
  system_instructions: "Route every request.",
  allowed_tools: ["create_task"],
  permissions: ["delegate_tasks"],
  provider: "demo",
  lifecycle: "active",
  runtime_state: "idle",
  is_central_manager: true,
  has_history: false,
  created_at: "2026-11-15T10:00:00Z",
  updated_at: "2026-11-15T10:00:00Z",
  disabled_at: null,
};

/** Mina works in the office of ward 111 (Study Upazila › Academic Management › Ward 1). */
export const MINA: Agent = {
  ...CENTRAL_MANAGER,
  id: 2,
  display_name: "Mina",
  avatar_key: "student",
  role: "Study Assistant",
  description: "Helps with study planning and exam preparation.",
  template_id: 4,
  template_key: "study_assistant",
  template_name: "Study Assistant",
  office_id: 1111,
  location: {
    office: { id: 1111, name: "Class Routine Office", kind: "ward" },
    ward: { id: 111, number: 1, name: "Class Routine" },
    union: { id: 11, name: "Academic Management" },
    upazila: { id: 1, name: "Study Upazila" },
    path: "Study Upazila › Academic Management › Ward 1: Class Routine",
  },
  system_instructions: "You are a study assistant.",
  allowed_tools: ["read_documents", "read_calendar"],
  permissions: ["read_upazila_memory"],
  is_central_manager: false,
};

const MANAGER_REF = { id: 1, display_name: "Central Manager", role: "Village Manager", avatar_key: "manager", is_central_manager: true };
const MINA_REF = { id: 2, display_name: "Mina", role: "Study Assistant", avatar_key: "student", is_central_manager: false };

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 1,
    title: "help me prepare for my exam",
    description: "",
    created_by: "chairman",
    created_by_name: "chairman",
    assigned_agent: null,
    parent_task_id: null,
    depth: 0,
    priority: "normal",
    input: {},
    output: null,
    status: "QUEUED",
    child_count: 0,
    created_at: "2026-11-15T10:00:00Z",
    started_at: null,
    completed_at: null,
    error: null,
    ...overrides,
  };
}

/** A finished request: routed to Study Upazila, answered by Mina, reported by the Central Manager. */
export const DONE_TASK: TaskDetail = {
  ...makeTask({
    status: "SUCCEEDED",
    assigned_agent: MANAGER_REF,
    child_count: 1,
    output: "[Demo] Central Manager report\nRequest: help me prepare for my exam",
    started_at: "2026-11-15T10:00:01Z",
    completed_at: "2026-11-15T10:00:03Z",
  }),
  children: [
    makeTask({
      id: 2,
      parent_task_id: 1,
      depth: 1,
      created_by: "agent:1",
      created_by_name: "Central Manager",
      assigned_agent: MINA_REF,
      status: "SUCCEEDED",
      output: "[Demo] Mina (Study Assistant)\nThis is a Demo Mode reply.",
      started_at: "2026-11-15T10:00:01Z",
      completed_at: "2026-11-15T10:00:02Z",
    }),
  ],
  messages: [
    {
      id: 1,
      sender: MANAGER_REF,
      receiver: MINA_REF,
      task_id: 2,
      type: "delegation",
      payload: {
        parent_task_id: 1,
        routing: {
          upazila_name: "Study Upazila",
          matched_keywords: ["exam"],
          agent_id: 2,
          agent_name: "Mina",
          agent_role: "Study Assistant",
          agent_path: "Study Upazila › Academic Management › Ward 1: Class Routine",
          active_candidates: 1,
          method: "demo keyword routing",
        },
      },
      created_at: "2026-11-15T10:00:01Z",
    },
    {
      id: 2,
      sender: MINA_REF,
      receiver: MANAGER_REF,
      task_id: 2,
      type: "result",
      payload: { parent_task_id: 1, status: "SUCCEEDED", output: "[Demo] Mina (Study Assistant)" },
      created_at: "2026-11-15T10:00:02Z",
    },
  ],
};
