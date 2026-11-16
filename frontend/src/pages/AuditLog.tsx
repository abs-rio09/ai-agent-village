import { ChevronLeft, ChevronRight, FilterX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage, type AuditEntry, type AuditPage } from "../api";
import { Badge, formatTime } from "../components/agents";
import { PageHeader } from "../components/org";
import { Button, ErrorBanner } from "../components/ui";
import { useIsMobile } from "../hooks";

// Audit Log: who did what, when, and how it was decided. Read-only — the server has no way to
// change or delete an entry.

export const PAGE_SIZE = 50;

const GROUP_LABELS: Record<string, string> = {
  tool: "Tools",
  approval: "Approvals",
  agent: "Agents",
  auth: "Logins & sessions",
  settings: "Settings",
  memory: "Memory",
  schedule: "Schedules",
};

function who(entry: AuditEntry): string {
  if (entry.actor.startsWith("chairman:")) return `Chairman (${entry.actor.slice("chairman:".length)})`;
  if (entry.actor.startsWith("agent:")) return entry.agent_name ? `Agent ${entry.agent_name}` : `Agent #${entry.actor.slice("agent:".length)}`;
  return entry.actor === "system" ? "System" : entry.actor;
}

function decisionTone(decision: string | null): "good" | "bad" | "warn" | "muted" {
  if (decision === "allowed" || decision === "approved") return "good";
  if (decision === "denied" || decision === "rejected") return "bad";
  if (decision === "pending") return "warn";
  return "muted";
}

function positive(value: string | null): number | null {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

export default function AuditLog({ timezone }: { timezone?: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const action = searchParams.get("action") ?? "";
  const agentId = positive(searchParams.get("agent_id"));
  const taskId = positive(searchParams.get("task_id"));
  const offset = Math.max(0, Number(searchParams.get("offset")) || 0);
  const [page, setPage] = useState<AuditPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isMobile = useIsMobile();

  const load = useCallback(async () => {
    try {
      setPage(await api.audit({ action: action || null, agent_id: agentId, task_id: taskId, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the audit log."));
    }
  }, [action, agentId, taskId, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Change one filter; any change goes back to the first page. */
  function setFilter(name: "action" | "agent_id" | "task_id", value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("offset");
    setSearchParams(next);
  }
  function goTo(newOffset: number) {
    const next = new URLSearchParams(searchParams);
    if (newOffset > 0) next.set("offset", String(newOffset));
    else next.delete("offset");
    setSearchParams(next);
  }

  const actions = page?.actions ?? [];
  const groups = Array.from(new Set(actions.map((item) => item.split(".")[0] ?? item)));
  const filtered = Boolean(action || agentId || taskId);
  const items = page?.items ?? [];
  const from = page && page.total > 0 ? page.offset + 1 : 0;
  const to = page ? page.offset + items.length : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Audit Log"
        intro="Every tool an agent used or was refused, every approval decision, every agent that was created, paused or disabled, and every login. Entries can only be added — never edited or deleted. Passwords, tokens and keys are never written here."
      />
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <section className="panel grid gap-3 p-4 sm:grid-cols-[1fr_9rem_9rem_auto] sm:items-end" aria-label="Filters">
        <div>
          <label htmlFor="audit-action" className="eyebrow mb-1.5 block">
            Action
          </label>
          <select id="audit-action" className="input" value={action} onChange={(event) => setFilter("action", event.target.value)}>
            <option value="">All actions</option>
            <optgroup label="Groups">
              {groups.map((group) => (
                <option key={group} value={group}>
                  {GROUP_LABELS[group] ?? group} (all)
                </option>
              ))}
            </optgroup>
            <optgroup label="Single actions">
              {actions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </optgroup>
            {/* keep a filter from the address bar selectable even when the log has no such entry */}
            {action && !groups.includes(action) && !actions.includes(action) && <option value={action}>{action}</option>}
          </select>
        </div>
        <div>
          <label htmlFor="audit-agent" className="eyebrow mb-1.5 block">
            Agent #
          </label>
          <input
            id="audit-agent"
            className="input"
            inputMode="numeric"
            placeholder="any"
            value={agentId ?? ""}
            onChange={(event) => setFilter("agent_id", event.target.value.replace(/\D/g, ""))}
          />
        </div>
        <div>
          <label htmlFor="audit-task" className="eyebrow mb-1.5 block">
            Task #
          </label>
          <input
            id="audit-task"
            className="input"
            inputMode="numeric"
            placeholder="any"
            value={taskId ?? ""}
            onChange={(event) => setFilter("task_id", event.target.value.replace(/\D/g, ""))}
          />
        </div>
        <Button variant="ghost" disabled={!filtered} icon={<FilterX size={16} aria-hidden="true" />} onClick={() => setSearchParams({})}>
          Clear
        </Button>
      </section>

      <section className="panel p-4" aria-label="Audit entries">
        {page === null ? (
          !error && <p className="text-sm text-mist-400">Loading the audit log…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-mist-400">{filtered ? "No entry matches these filters." : "The audit log is empty."}</p>
        ) : isMobile ? (
          <ul className="divide-y divide-night-700/70">
            {items.map((entry) => (
              <li key={entry.id} className="space-y-1 py-3" aria-label={`Entry ${entry.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-mist-50">{entry.action}</span>
                  {entry.decision && <Badge tone={decisionTone(entry.decision)}>{entry.decision}</Badge>}
                </div>
                <p className="break-words text-sm text-mist-100">{entry.summary}</p>
                <p className="text-xs text-mist-400">
                  {who(entry)}
                  {entry.tool_key && <> · {entry.tool_key}</>}
                  {entry.task_id !== null && (
                    <>
                      {" "}
                      ·{" "}
                      <Link to={`/tasks?id=${entry.task_id}`} className="text-lantern-300">
                        task #{entry.task_id}
                      </Link>
                    </>
                  )}
                </p>
                <p className="font-mono text-[11px] text-mist-500">{formatTime(entry.created_at, timezone)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <div className="thin-scroll overflow-x-auto">
            <table className="w-full min-w-[52rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-night-600 text-xs uppercase tracking-wider text-mist-400">
                  {["Time", "Who", "Action", "Agent", "Task", "Tool", "Decision", "Summary"].map((heading) => (
                    <th key={heading} scope="col" className="px-2 py-2 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((entry) => (
                  <tr key={entry.id} className="border-b border-night-700/70 align-top">
                    <td className="whitespace-nowrap px-2 py-2 font-mono text-[11px] text-mist-400">{formatTime(entry.created_at, timezone)}</td>
                    <td className="px-2 py-2 text-mist-100">{who(entry)}</td>
                    <td className="px-2 py-2 font-mono text-xs text-mist-50">{entry.action}</td>
                    <td className="px-2 py-2">
                      {entry.agent_id !== null ? (
                        <button
                          type="button"
                          className="text-left text-lantern-300 underline-offset-4 hover:underline"
                          title="Show only this agent"
                          onClick={() => setFilter("agent_id", String(entry.agent_id))}
                        >
                          {entry.agent_name ?? `#${entry.agent_id}`}
                        </button>
                      ) : (
                        <span className="text-mist-500">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      {entry.task_id !== null ? (
                        <Link to={`/tasks?id=${entry.task_id}`} className="text-lantern-300 underline-offset-4 hover:underline">
                          #{entry.task_id}
                        </Link>
                      ) : (
                        <span className="text-mist-500">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2 font-mono text-xs text-mist-300">{entry.tool_key ?? "—"}</td>
                    <td className="px-2 py-2">{entry.decision ? <Badge tone={decisionTone(entry.decision)}>{entry.decision}</Badge> : <span className="text-mist-500">—</span>}</td>
                    <td className="max-w-md break-words px-2 py-2 text-mist-100">{entry.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {page !== null && page.total > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="font-mono text-xs text-mist-400" data-testid="audit-range">
              {from}–{to} of {page.total}
            </p>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={page.offset === 0}
                icon={<ChevronLeft size={14} aria-hidden="true" />}
                onClick={() => goTo(Math.max(0, page.offset - PAGE_SIZE))}
              >
                Newer
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={to >= page.total}
                icon={<ChevronRight size={14} aria-hidden="true" />}
                onClick={() => goTo(page.offset + PAGE_SIZE)}
              >
                Older
              </Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
