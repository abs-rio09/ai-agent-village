// Shared pieces of the agent and task pages: the robot avatar, status badges, the office
// picker (Upazila → Union → Ward) and the tools / permissions checklist.

import { useState, type ReactNode } from "react";

import type { CatalogItem, Lifecycle, OrgTree, RuntimeState, TaskStatus } from "../api";
import { cx } from "./ui";

// ---------------------------------------------------------------- avatar

// A small humanoid robot drawn in SVG. The uniform colour and one accessory depend on the
// agent's avatar_key; unknown keys get the plain robot. No image files are loaded.
const UNIFORMS: Record<string, { color: string; accessory: ReactNode }> = {
  manager: {
    color: "var(--color-lantern-400)",
    accessory: (
      <>
        <path d="M24 30l-2 3 2 6 2-6z" fill="var(--color-night-900)" />
        <rect x="28.5" y="31" width="4" height="3" rx="0.6" fill="var(--color-mist-50)" />
      </>
    ),
  },
  office: {
    color: "var(--color-river-400)",
    accessory: <rect x="20.5" y="31" width="7" height="8" rx="1" fill="var(--color-mist-50)" opacity="0.9" />,
  },
  helper: {
    color: "var(--color-paddy-500)",
    accessory: <path d="M13 12h22l-2-4.5H15z" fill="var(--color-paddy-400)" />,
  },
  student: {
    color: "var(--color-river-300)",
    accessory: <path d="M18 32h5.5v6H18zM24.5 32H30v6h-5.5z" fill="var(--color-night-900)" opacity="0.75" />,
  },
  teacher: {
    color: "var(--color-paddy-400)",
    accessory: <path d="M16 9l8-3.5L32 9l-8 3.5z" fill="var(--color-mist-100)" />,
  },
  librarian: {
    color: "var(--color-lantern-300)",
    accessory: (
      <>
        <rect x="18" y="31" width="12" height="2.4" rx="0.5" fill="var(--color-night-900)" opacity="0.8" />
        <rect x="19" y="34.2" width="10" height="2.4" rx="0.5" fill="var(--color-night-900)" opacity="0.6" />
      </>
    ),
  },
  business: {
    color: "var(--color-mist-300)",
    accessory: <path d="M19 33h10v6H19zM22 33v-2h4v2" fill="none" stroke="var(--color-night-900)" strokeWidth="1.4" />,
  },
  sales: {
    color: "var(--color-lantern-500)",
    accessory: <path d="M20 32h6l3 3.5-3 3.5h-6z" fill="var(--color-mist-50)" opacity="0.9" />,
  },
  support: {
    color: "var(--color-river-400)",
    accessory: <path d="M11.5 19a12.5 12.5 0 0 1 25 0" fill="none" stroke="var(--color-mist-100)" strokeWidth="1.8" strokeLinecap="round" />,
  },
  accountant: {
    color: "var(--color-paddy-300)",
    accessory: <circle cx="24" cy="35" r="3.4" fill="none" stroke="var(--color-night-900)" strokeWidth="1.5" />,
  },
  reporter: {
    color: "var(--color-mist-400)",
    accessory: <path d="M19 32h10M19 35h10M19 38h6" stroke="var(--color-night-900)" strokeWidth="1.3" strokeLinecap="round" />,
  },
  doctor: {
    color: "var(--color-mist-50)",
    accessory: <path d="M24 31.5v7M20.5 35h7" stroke="var(--color-clay-400)" strokeWidth="2" strokeLinecap="round" />,
  },
  technician: {
    color: "var(--color-clay-400)",
    accessory: (
      <>
        <rect x="14" y="36" width="20" height="2.4" fill="var(--color-night-900)" opacity="0.75" />
        <rect x="26" y="34" width="3" height="6" rx="0.6" fill="var(--color-mist-100)" />
      </>
    ),
  },
  techsupport: {
    color: "var(--color-river-300)",
    accessory: (
      <>
        <path d="M11.5 19a12.5 12.5 0 0 1 25 0" fill="none" stroke="var(--color-mist-100)" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="24" cy="35" r="2.6" fill="none" stroke="var(--color-night-900)" strokeWidth="1.4" strokeDasharray="2 1.4" />
      </>
    ),
  },
  project: {
    color: "var(--color-lantern-300)",
    accessory: (
      <>
        <rect x="18" y="31.5" width="7" height="2" rx="0.5" fill="var(--color-night-900)" opacity="0.8" />
        <rect x="21" y="34.5" width="8" height="2" rx="0.5" fill="var(--color-night-900)" opacity="0.65" />
        <rect x="19" y="37.5" width="5" height="2" rx="0.5" fill="var(--color-night-900)" opacity="0.5" />
      </>
    ),
  },
};

export function AgentAvatar({ avatarKey, size = 48 }: { avatarKey: string; size?: number }) {
  const uniform = UNIFORMS[avatarKey];
  const color = uniform?.color ?? "var(--color-mist-400)";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      data-avatar={uniform ? avatarKey : "default"}
      className="shrink-0 rounded-2xl border border-night-600 bg-night-800"
    >
      <path d="M24 9V5.5" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="24" cy="4.6" r="1.6" fill={color} />
      <rect x="13" y="9" width="22" height="16" rx="6" fill="var(--color-night-700)" stroke={color} strokeWidth="1.5" />
      <circle cx="19.5" cy="17" r="2.1" fill="var(--color-river-300)" />
      <circle cx="28.5" cy="17" r="2.1" fill="var(--color-river-300)" />
      <path d="M21 21.5h6" stroke="var(--color-mist-400)" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M14 43V33a5 5 0 0 1 5-5h10a5 5 0 0 1 5 5v10z" fill={color} />
      {uniform?.accessory}
    </svg>
  );
}

// ---------------------------------------------------------------- badges

function Badge({ tone, children, testId }: { tone: "good" | "warn" | "bad" | "info" | "muted"; children: ReactNode; testId?: string }) {
  return (
    <span
      data-testid={testId}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em]",
        tone === "good" && "border-paddy-500/40 bg-paddy-500/10 text-paddy-300",
        tone === "warn" && "border-lantern-500/40 bg-lantern-500/10 text-lantern-200",
        tone === "bad" && "border-clay-500/40 bg-clay-500/10 text-clay-300",
        tone === "info" && "border-river-400/40 bg-river-400/10 text-river-300",
        tone === "muted" && "border-night-600 bg-night-800 text-mist-400",
      )}
    >
      {children}
    </span>
  );
}

const LIFECYCLE_TONE: Record<Lifecycle, "good" | "warn" | "muted"> = { active: "good", paused: "warn", disabled: "muted" };

export function LifecycleBadge({ lifecycle }: { lifecycle: Lifecycle }) {
  return (
    <Badge tone={LIFECYCLE_TONE[lifecycle]} testId="lifecycle-badge">
      {lifecycle}
    </Badge>
  );
}

const RUNTIME_TONE: Record<RuntimeState, "good" | "warn" | "info" | "muted"> = {
  idle: "muted",
  working: "info",
  waiting: "warn",
  offline: "muted",
};

export function RuntimeBadge({ state }: { state: RuntimeState }) {
  return (
    <Badge tone={RUNTIME_TONE[state]} testId="runtime-badge">
      <span
        aria-hidden="true"
        className={cx(
          "size-1.5 rounded-full",
          state === "working" ? "animate-beacon bg-river-400" : state === "waiting" ? "bg-lantern-400" : state === "idle" ? "bg-paddy-400" : "bg-night-500",
        )}
      />
      {state}
    </Badge>
  );
}

const STATUS_TONE: Record<TaskStatus, "good" | "warn" | "bad" | "info" | "muted"> = {
  QUEUED: "muted",
  ASSIGNED: "warn",
  RUNNING: "info",
  WAITING_APPROVAL: "warn",
  SUCCEEDED: "good",
  FAILED: "bad",
  CANCELLED: "muted",
};

/** A task that is not finished yet: the pages keep polling while one of these exists. */
export function isActiveStatus(status: TaskStatus): boolean {
  return status === "QUEUED" || status === "ASSIGNED" || status === "RUNNING" || status === "WAITING_APPROVAL";
}

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge tone={STATUS_TONE[status]} testId="task-status">
      {status.replace("_", " ")}
    </Badge>
  );
}

// ---------------------------------------------------------------- office picker

interface OfficePickerProps {
  tree: OrgTree;
  /** The chosen office id, or null while nothing valid is chosen. */
  value: number | null;
  onChange: (officeId: number | null) => void;
  idPrefix: string;
}

const CENTRAL = "central";

function locate(tree: OrgTree, officeId: number | null): { place: string; unionId: number | null } {
  if (officeId === null) return { place: "", unionId: null };
  if (tree.central_office?.id === officeId) return { place: CENTRAL, unionId: null };
  for (const upazila of tree.upazilas) {
    for (const union of upazila.unions) {
      if (union.wards.some((ward) => ward.office?.id === officeId)) return { place: String(upazila.id), unionId: union.id };
    }
  }
  return { place: "", unionId: null };
}

/**
 * Pick an Office the way the village is organised: Upazila → Union → Ward (every Ward has one
 * Office). "Central Administration" is the village's own office and has no Union or Ward.
 */
export function OfficePicker({ tree, value, onChange, idPrefix }: OfficePickerProps) {
  const [selection, setSelection] = useState(() => locate(tree, value));
  const upazila = tree.upazilas.find((item) => String(item.id) === selection.place) ?? null;
  const union = upazila?.unions.find((item) => item.id === selection.unionId) ?? null;
  const wards = (union?.wards ?? []).filter((ward) => ward.office !== null);
  const ward = wards.find((item) => item.office?.id === value) ?? null;

  function choosePlace(place: string) {
    if (place === CENTRAL) {
      setSelection({ place, unionId: null });
      onChange(tree.central_office?.id ?? null);
      return;
    }
    const chosen = tree.upazilas.find((item) => String(item.id) === place);
    const firstUnion = chosen?.unions[0] ?? null;
    setSelection({ place, unionId: firstUnion?.id ?? null });
    onChange(firstUnion?.wards.find((item) => item.office)?.office?.id ?? null);
  }

  function chooseUnion(unionId: number) {
    setSelection({ place: selection.place, unionId });
    const chosen = upazila?.unions.find((item) => item.id === unionId);
    onChange(chosen?.wards.find((item) => item.office)?.office?.id ?? null);
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div>
        <label htmlFor={`${idPrefix}-upazila`} className="eyebrow mb-1.5 block">
          Upazila
        </label>
        <select id={`${idPrefix}-upazila`} className="input" value={selection.place} onChange={(event) => choosePlace(event.target.value)}>
          <option value="" disabled>
            Choose…
          </option>
          {tree.upazilas.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
          {tree.central_office && <option value={CENTRAL}>{tree.central_office.name} (village office)</option>}
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-union`} className="eyebrow mb-1.5 block">
          Union
        </label>
        <select
          id={`${idPrefix}-union`}
          className="input"
          value={union?.id ?? ""}
          disabled={!upazila || upazila.unions.length === 0}
          onChange={(event) => chooseUnion(Number(event.target.value))}
        >
          {!union && <option value="">{upazila ? "No Unions yet" : "—"}</option>}
          {upazila?.unions.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-ward`} className="eyebrow mb-1.5 block">
          Ward
        </label>
        <select
          id={`${idPrefix}-ward`}
          className="input"
          value={ward?.id ?? ""}
          disabled={wards.length === 0}
          onChange={(event) => onChange(wards.find((item) => item.id === Number(event.target.value))?.office?.id ?? null)}
        >
          {!ward && <option value="">{union ? "No Wards yet" : "—"}</option>}
          {wards.map((item) => (
            <option key={item.id} value={item.id}>
              {`Ward ${item.number}: ${item.name}`}
            </option>
          ))}
        </select>
      </div>
      <p className="text-xs text-mist-500 sm:col-span-3">
        {selection.place === CENTRAL
          ? "Central Administration is the village's own office. It has no Union or Ward, and the Central Manager only sends tasks to agents inside an Upazila."
          : ward
            ? `Office: ${ward.office?.name}`
            : upazila
              ? "This Upazila has no Ward with an Office here yet. Add Unions and Wards first, or pick another one."
              : "Every Ward has one Office. Pick the Upazila, then the Union and the Ward."}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- tools + permissions

export function EnforcementNote() {
  return (
    <p role="note" className="rounded-xl border border-lantern-500/30 bg-lantern-500/10 px-4 py-3 text-sm text-lantern-200">
      Tools and permissions are saved with the agent, but they are <strong className="font-semibold">not enforced yet</strong>: they
      will be enforced in M4. Until then no tool can be run and nothing is limited by these choices.
    </p>
  );
}

interface ChecklistProps {
  legend: string;
  items: CatalogItem[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

export function CatalogChecklist({ legend, items, selected, onChange }: ChecklistProps) {
  function toggle(key: string, checked: boolean) {
    // keep the catalogue's order, whatever order the boxes were ticked in
    onChange(items.map((item) => item.key).filter((item) => (item === key ? checked : selected.includes(item))));
  }
  return (
    <fieldset>
      <legend className="eyebrow mb-2">{legend}</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <label
            key={item.key}
            className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-night-700 bg-night-900/60 px-3 py-2.5 transition hover:border-night-500"
          >
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-[var(--color-lantern-400)]"
              checked={selected.includes(item.key)}
              onChange={(event) => toggle(item.key, event.target.checked)}
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-mist-50">
                {item.label}
                {item.sensitive && (
                  <span className="ml-2 rounded border border-clay-500/40 px-1 font-mono text-[10px] uppercase tracking-wider text-clay-300">
                    needs approval
                  </span>
                )}
              </span>
              <span className="block text-xs text-mist-400">{item.description}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// ---------------------------------------------------------------- small helpers

export const INSTRUCTIONS_MAX = 4000;

export function formatTime(value: string | null, timezone?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium", timeZone: timezone }).format(date);
  } catch {
    return date.toISOString();
  }
}
