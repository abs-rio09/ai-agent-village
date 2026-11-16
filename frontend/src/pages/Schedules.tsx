import { CalendarClock, Pause, Play, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { api, errorMessage, type Agent, type Schedule, type SchedulesPage } from "../api";
import { Badge, TaskStatusBadge, formatTime } from "../components/agents";
import { Dialog } from "../components/Dialog";
import { PageHeader } from "../components/org";
import { Button, ErrorBanner } from "../components/ui";

// Schedules: a schedule only CREATES a task (for one agent, at an interval or a time of day).
// The task runner does the work, with the same permission checks as any other task.

export const POLL_MS = 10_000;
const REQUEST_MAX = 4000;

function ConfirmDelete({ schedule, onDone, onClose }: { schedule: Schedule; onDone: () => Promise<void>; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteSchedule(schedule.id);
      await onDone();
      onClose();
    } catch (cause) {
      setError(errorMessage(cause, "The schedule could not be deleted."));
      setBusy(false);
    }
  }
  return (
    <Dialog title="Delete this schedule?" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-mist-300">
          <strong className="font-semibold text-mist-50">{schedule.name}</strong> ({schedule.trigger_text}) will create no more tasks.
          The tasks it already created are kept.
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" busy={busy} data-autofocus onClick={() => void remove()}>
            Delete schedule
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function CreateForm({ agents, timezone, onCreated }: { agents: Agent[]; timezone: string; onCreated: () => Promise<void> }) {
  const [agentId, setAgentId] = useState<number | "">("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"interval" | "daily">("interval");
  const [minutes, setMinutes] = useState("60");
  const [time, setTime] = useState("09:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosen = agentId === "" ? agents[0]?.id : agentId;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const interval = Number(minutes);
    if (chosen === undefined) return setError("Create an agent first: a schedule needs an agent to give its task to.");
    if (!text.trim()) return setError("Write what the agent should do.");
    if (kind === "interval" && (!Number.isInteger(interval) || interval < 1 || interval > 10080)) {
      return setError("The interval must be between 1 and 10080 minutes (one week).");
    }
    if (kind === "daily" && !/^\d{2}:\d{2}$/.test(time)) return setError("Choose the time of day.");
    setBusy(true);
    setError(null);
    try {
      await api.createSchedule(
        kind === "interval"
          ? { agent_id: chosen, request_text: text.trim(), trigger_type: "interval", interval_minutes: interval }
          : { agent_id: chosen, request_text: text.trim(), trigger_type: "daily", daily_time: time },
      );
      setText("");
      await onCreated();
    } catch (cause) {
      setError(errorMessage(cause, "The schedule could not be created."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="panel space-y-3 p-5" aria-label="New schedule">
      <h2 className="eyebrow">New schedule</h2>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="schedule-agent" className="mb-1.5 block text-sm font-medium text-mist-100">
            Agent
          </label>
          <select id="schedule-agent" className="input" value={chosen ?? ""} onChange={(event) => setAgentId(Number(event.target.value))}>
            {agents.length === 0 && <option value="">No agent yet</option>}
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.display_name} ({agent.role}){agent.lifecycle === "active" ? "" : ` — ${agent.lifecycle}`}
              </option>
            ))}
          </select>
        </div>
        <fieldset>
          <legend className="mb-1.5 block text-sm font-medium text-mist-100">When</legend>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-mist-100">
            <label className="flex min-h-11 items-center gap-2 sm:min-h-0">
              <input type="radio" name="schedule-kind" checked={kind === "interval"} onChange={() => setKind("interval")} />
              Every
              <input
                aria-label="Interval in minutes"
                className="input !w-20"
                inputMode="numeric"
                value={minutes}
                onFocus={() => setKind("interval")}
                onChange={(event) => setMinutes(event.target.value.replace(/\D/g, ""))}
              />
              minutes
            </label>
            <label className="flex min-h-11 items-center gap-2 sm:min-h-0">
              <input type="radio" name="schedule-kind" checked={kind === "daily"} onChange={() => setKind("daily")} />
              Every day at
              <input
                aria-label="Time of day"
                type="time"
                className="input !w-28"
                value={time}
                onFocus={() => setKind("daily")}
                onChange={(event) => setTime(event.target.value)}
              />
            </label>
          </div>
          <p className="mt-1 text-xs text-mist-500">Times are in the village&apos;s timezone ({timezone}).</p>
        </fieldset>
      </div>
      <div>
        <label htmlFor="schedule-text" className="mb-1.5 block text-sm font-medium text-mist-100">
          Request
        </label>
        <textarea
          id="schedule-text"
          className="input min-h-16"
          maxLength={REQUEST_MAX}
          placeholder="For example: summarise today's study progress"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </div>
      <div className="flex justify-end">
        <Button type="submit" busy={busy} icon={<CalendarClock size={16} aria-hidden="true" />}>
          Create schedule
        </Button>
      </div>
    </form>
  );
}

export default function Schedules({ timezone, pollMs = POLL_MS }: { timezone?: string; pollMs?: number }) {
  const [page, setPage] = useState<SchedulesPage | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Schedule | null>(null);

  const reload = useCallback(async () => {
    try {
      setPage(await api.schedules());
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the schedules."));
    }
  }, []);

  useEffect(() => {
    void reload();
    void api
      .agents()
      .then((list) => setAgents(list.filter((agent) => !agent.is_central_manager)))
      .catch(() => undefined);
    const timer = window.setInterval(() => void reload(), pollMs); // last run / next run move on their own
    return () => window.clearInterval(timer);
  }, [reload, pollMs]);

  async function toggle(schedule: Schedule) {
    setBusyId(schedule.id);
    try {
      await api.scheduleAction(schedule.id, schedule.paused ? "resume" : "pause");
      await reload();
    } catch (cause) {
      setError(errorMessage(cause, "The schedule could not be changed."));
    } finally {
      setBusyId(null);
    }
  }

  const zone = page?.timezone ?? timezone ?? "Asia/Dhaka";
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Schedules"
        intro="A schedule creates a task by itself — every so many minutes, or once a day — and gives it to one agent. The task then runs like any other task, with the same permission checks."
      />
      {page !== null && !page.scheduler_running && (
        <p role="alert" className="rounded-xl border border-clay-500/40 bg-clay-500/10 px-4 py-3 text-sm text-clay-300">
          The scheduler is not running, so no schedule creates tasks right now. Run <code className="font-mono">./village doctor</code> to
          see why.
        </p>
      )}
      <p role="note" className="rounded-xl border border-night-600 bg-night-900/60 px-4 py-3 text-sm text-mist-300">
        Schedules run only while this PC is on and the village is started. Runs missed while it was off are folded into one run at
        the next start — never one task per missed run.
      </p>
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <CreateForm agents={agents} timezone={zone} onCreated={reload} />

      <section className="panel p-5" aria-label="Schedules">
        <h2 className="eyebrow">All schedules</h2>
        {page === null ? (
          !error && <p className="mt-3 text-sm text-mist-400">Loading the schedules…</p>
        ) : (
          <ul className="mt-3 divide-y divide-night-700/70">
            {page.schedules.map((schedule) => (
              <li key={schedule.id} className="space-y-2 py-4" aria-label={`Schedule ${schedule.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="min-w-0 break-words text-sm font-semibold text-mist-50">{schedule.name}</h3>
                  {schedule.kind === "builtin" && <Badge tone="info">built-in</Badge>}
                  <Badge tone={schedule.paused ? "warn" : "good"} testId="schedule-state">
                    {schedule.paused ? "paused" : "active"}
                  </Badge>
                </div>
                <p className="text-sm text-mist-300">
                  <span className="font-medium text-mist-100">{schedule.trigger_text}</span>
                  {schedule.agent ? (
                    <>
                      {" "}
                      → task for{" "}
                      <Link to={`/agents/profile?id=${schedule.agent.id}`} className="text-lantern-300 underline-offset-4 hover:underline">
                        {schedule.agent.display_name}
                      </Link>
                      : “{schedule.request_text}”
                    </>
                  ) : (
                    <> — {schedule.request_text}</>
                  )}
                </p>
                <dl className="grid gap-x-8 gap-y-1 text-xs text-mist-400 sm:grid-cols-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <dt>Last run:</dt>
                    <dd className="flex flex-wrap items-center gap-2 font-mono text-mist-100">
                      {schedule.last_run_at ? formatTime(schedule.last_run_at, zone) : "never"}
                      {schedule.last_task_id !== null && (
                        <Link to={`/tasks?id=${schedule.last_task_id}`} className="font-sans text-lantern-300 underline-offset-4 hover:underline">
                          task #{schedule.last_task_id}
                        </Link>
                      )}
                      {schedule.last_task_status && <TaskStatusBadge status={schedule.last_task_status} />}
                    </dd>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <dt>Next run:</dt>
                    <dd className="font-mono text-mist-100" data-testid="next-run">
                      {schedule.paused ? "paused" : schedule.next_run_at ? formatTime(schedule.next_run_at, zone) : "—"}
                    </dd>
                  </div>
                </dl>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    busy={busyId === schedule.id}
                    icon={schedule.paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
                    onClick={() => void toggle(schedule)}
                  >
                    {schedule.paused ? "Resume" : "Pause"}
                  </Button>
                  {schedule.kind === "custom" && (
                    <Button variant="danger" size="sm" icon={<Trash2 size={14} aria-hidden="true" />} onClick={() => setDeleting(schedule)}>
                      Delete
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {deleting && <ConfirmDelete schedule={deleting} onDone={reload} onClose={() => setDeleting(null)} />}
    </div>
  );
}
