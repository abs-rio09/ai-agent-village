// Shared pieces of the agent and task pages: status badges, the office picker (Upazila → Union →
// Ward) and the tools / permissions checklist. The robot avatar lives in components/robots.

import { useState, type ReactNode } from "react";

import type { CatalogItem, Lifecycle, OrgTree, RuntimeState, TaskStatus } from "../api";
import { cx } from "./ui";

// ---------------------------------------------------------------- badges

export function Badge({ tone, children, testId }: { tone: "good" | "warn" | "bad" | "info" | "muted"; children: ReactNode; testId?: string }) {
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
    <p role="note" className="rounded-xl border border-paddy-500/30 bg-paddy-500/10 px-4 py-3 text-sm text-paddy-200">
      Tools and permissions are <strong className="font-semibold">enforced</strong>: an agent can only use a tool that is ticked here,
      and only when it also has the permission that tool needs. Every use and every refusal is written to the audit log. A tool
      marked “not built yet” can be assigned, but it answers “not available yet”.
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
                {item.available === false && (
                  <span className="ml-2 rounded border border-night-500 px-1 font-mono text-[10px] uppercase tracking-wider text-mist-400">
                    not built yet
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
