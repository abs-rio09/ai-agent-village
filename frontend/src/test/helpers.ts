import { vi } from "vitest";

import type { Health, OrgTree, OverviewStats, Template, TreeUnion, TreeUpazila, User, Village } from "../api";

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

export const STATS: OverviewStats = { upazilas: 2, unions: 5, wards: 45, offices: 46, ward_offices: 45 };

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
  },
  {
    key: "business",
    name: "Business Upazila",
    description: "",
    icon: "store",
    sort_order: 2,
    unions: [{ id: 6, name: "Business Strategy", sort_order: 1 }],
    wards: [{ id: 10, number: 1, name: "Ward 1", responsibility: "" }],
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
    upazilas,
  };
}
