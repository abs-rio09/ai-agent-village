import { ArrowLeft, Ban, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage, type AgentMessage, type Routing, type Task, type TaskDetail, type TaskPriority } from "../api";
import { AgentAvatar, TaskStatusBadge, formatTime, isActiveStatus } from "../components/agents";
import { PageHeader, plural } from "../components/org";
import { Button, ErrorBanner, cx } from "../components/ui";
import { useIsMobile } from "../hooks";

// Task Center: send a request to the Central Manager and follow it. The background worker on the
// server does the work; this page only reads. It polls while a task is unfinished and stops
// polling as soon as nothing is active.

const TITLE_MAX = 200;
const DETAILS_MAX = 4000;
export const POLL_MS = 1500;

function Output({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="eyebrow mb-1.5">{label}</p>
      <pre className="thin-scroll max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-night-700 bg-night-900/70 p-3 font-mono text-xs leading-relaxed text-mist-100">
        {text}
      </pre>
    </div>
  );
}

function RoutingResult({ task }: { task: TaskDetail }) {
  const routings = task.messages
    .filter((message) => message.type === "delegation" && message.payload.routing)
    .map((message) => message.payload.routing as Routing);
  return (
    <section aria-label="Routing result">
      <p className="eyebrow mb-1.5">Routing result</p>
      {routings.length > 0 ? (
        routings.map((routing, index) => (
          <p key={index} className="text-sm leading-relaxed text-mist-100">
            Routed to <strong className="font-semibold text-mist-50">{routing.upazila_name}</strong> (matched keywords:{" "}
            {(routing.matched_keywords ?? []).join(", ") || "none"}) and delegated to{" "}
            {routing.agent_id ? (
              <Link to={`/agents/profile?id=${routing.agent_id}`} className="font-semibold text-lantern-300 underline-offset-4 hover:underline">
                {routing.agent_name}
              </Link>
            ) : (
              routing.agent_name
            )}{" "}
            ({routing.agent_role}), {routing.agent_path}.{" "}
            <span className="text-mist-400">
              Chosen among {plural(routing.active_candidates ?? 0, "active agent")} by {routing.method ?? "keyword routing"} — not by an AI model.
            </span>
          </p>
        ))
      ) : task.status === "FAILED" ? (
        <p className="text-sm text-mist-300">The request was not delegated. The reason is shown under “Error”.</p>
      ) : task.status === "CANCELLED" ? (
        <p className="text-sm text-mist-300">The request was cancelled before it was delegated.</p>
      ) : (
        <p className="text-sm text-mist-300">Waiting for the Central Manager to route this request…</p>
      )}
    </section>
  );
}

function MessageRow({ message, timezone }: { message: AgentMessage; timezone?: string }) {
  const summary =
    message.type === "delegation"
      ? "Delegated the task"
      : message.payload.status === "SUCCEEDED"
        ? "Returned its result"
        : `Reported ${message.payload.status ?? "a result"}${message.payload.error ? `: ${message.payload.error}` : ""}`;
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2 text-sm">
      <span className="rounded border border-night-600 px-1.5 font-mono text-[10px] uppercase tracking-wider text-mist-400">{message.type}</span>
      <span className="text-mist-100">
        <strong className="font-semibold text-mist-50">{message.sender?.display_name ?? "?"}</strong> →{" "}
        <strong className="font-semibold text-mist-50">{message.receiver?.display_name ?? "?"}</strong>
      </span>
      <span className="min-w-0 flex-1 text-mist-300">
        {summary} (task #{message.task_id})
      </span>
      <span className="font-mono text-[11px] text-mist-500">{formatTime(message.created_at, timezone)}</span>
    </li>
  );
}

interface DetailProps {
  task: TaskDetail;
  timezone?: string;
  onCancel: () => Promise<void>;
}

function TaskDetailPanel({ task, timezone, onCancel }: DetailProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await onCancel();
    } catch (cause) {
      setError(errorMessage(cause, "The task could not be cancelled."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel space-y-5 p-5" aria-label={`Task ${task.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">Task #{task.id}</p>
          <h2 className="mt-1 text-lg font-semibold text-mist-50">{task.title}</h2>
          {task.description && <p className="mt-1 whitespace-pre-wrap text-sm text-mist-300">{task.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          <TaskStatusBadge status={task.status} />
          {isActiveStatus(task.status) && (
            <Button variant="danger" size="sm" busy={busy} icon={<Ban size={14} aria-hidden="true" />} onClick={() => void cancel()}>
              Cancel task
            </Button>
          )}
        </div>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <dl className="grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
        {[
          ["Created by", task.created_by_name],
          ["Assigned to", task.assigned_agent?.display_name ?? "not assigned yet"],
          ["Priority", task.priority],
          ["Created", formatTime(task.created_at, timezone)],
          ["Started", formatTime(task.started_at, timezone)],
          ["Completed", formatTime(task.completed_at, timezone)],
        ].map(([name, value]) => (
          <div key={name} className="flex items-baseline justify-between gap-4 border-t border-night-700/70 py-1.5">
            <dt className="text-xs text-mist-400">{name}</dt>
            <dd className="text-right font-mono text-[13px] text-mist-100">{value}</dd>
          </div>
        ))}
      </dl>

      <RoutingResult task={task} />

      {task.error && (
        <div>
          <p className="eyebrow mb-1.5">Error</p>
          <p role="alert" className="rounded-xl border border-clay-500/40 bg-clay-500/10 px-4 py-3 text-sm text-clay-300">
            {task.error}
          </p>
        </div>
      )}

      {task.output && <Output label="Final output" text={task.output} />}

      <section aria-label="Child tasks">
        <p className="eyebrow mb-1.5">Child tasks</p>
        {task.children.length === 0 ? (
          <p className="text-sm text-mist-400">No task has been delegated.</p>
        ) : (
          <ul className="space-y-3">
            {task.children.map((child) => (
              <li key={child.id} className="rounded-xl border border-night-700 p-3" aria-label={`Child task ${child.id}`}>
                <div className="flex flex-wrap items-center gap-3">
                  {child.assigned_agent && <AgentAvatar avatarKey={child.assigned_agent.avatar_key} size={36} />}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-mist-50">
                      #{child.id}{" "}
                      {child.assigned_agent ? (
                        <Link to={`/agents/profile?id=${child.assigned_agent.id}`} className="underline-offset-4 hover:text-lantern-300 hover:underline">
                          {child.assigned_agent.display_name}
                        </Link>
                      ) : (
                        "No agent"
                      )}
                      {child.assigned_agent && <span className="font-normal text-mist-400"> · {child.assigned_agent.role}</span>}
                    </p>
                    <p className="font-mono text-[11px] text-mist-500">
                      started {formatTime(child.started_at, timezone)} · completed {formatTime(child.completed_at, timezone)}
                    </p>
                  </div>
                  <TaskStatusBadge status={child.status} />
                </div>
                {child.error && <p className="mt-2 text-sm text-clay-300">{child.error}</p>}
                {child.output && (
                  <div className="mt-3">
                    <Output label="Reply" text={child.output} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Agent messages">
        <p className="eyebrow mb-1.5">Agent messages</p>
        {task.messages.length === 0 ? (
          <p className="text-sm text-mist-400">No messages yet.</p>
        ) : (
          <ul className="divide-y divide-night-700/70">
            {task.messages.map((message) => (
              <MessageRow key={message.id} message={message} timezone={timezone} />
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}

export default function Tasks({ timezone, pollMs = POLL_MS }: { timezone?: string; pollMs?: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [details, setDetails] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("normal");
  const [formError, setFormError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const isMobile = useIsMobile();
  const selectedId = Number(searchParams.get("id")) || null;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;

  const reload = useCallback(async () => {
    const wanted = selectedRef.current;
    try {
      const [list, one] = await Promise.all([api.tasks({ top_level: true }), wanted === null ? null : api.task(wanted)]);
      setTasks(list);
      if (selectedRef.current === wanted) setDetail(one); // ignore the answer for a task that is no longer open
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the tasks."));
    }
  }, []);

  useEffect(() => {
    setDetail(null);
    void reload();
  }, [reload, selectedId]);

  // Poll only while something is unfinished; the interval is removed as soon as all is done.
  const active = (tasks ?? []).some((task) => isActiveStatus(task.status)) || (detail !== null && isActiveStatus(detail.status));
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void reload(), pollMs);
    return () => window.clearInterval(timer);
  }, [active, pollMs, reload]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setFormError("Write what you need.");
      return;
    }
    setSending(true);
    setFormError(null);
    try {
      const task = await api.createTask({ title: title.trim(), description: details.trim(), priority });
      setTitle("");
      setDetails("");
      setPriority("normal");
      selectedRef.current = task.id;
      setSearchParams({ id: String(task.id) });
      await reload();
    } catch (cause) {
      setFormError(errorMessage(cause, "The request could not be sent."));
    } finally {
      setSending(false);
    }
  }

  const detailView =
    selectedId === null ? null : detail ? (
      <TaskDetailPanel
        task={detail}
        timezone={timezone}
        onCancel={async () => {
          try {
            await api.cancelTask(detail.id);
          } finally {
            await reload(); // also after a 409: show what the task really is now
          }
        }}
      />
    ) : (
      !error && <p className="text-sm text-mist-400">Loading task #{selectedId}…</p>
    );

  // On a phone an opened task takes the whole screen; "Back" returns to the form and the list.
  if (isMobile && selectedId !== null) {
    return (
      <div className="space-y-4">
        <Link
          to="/tasks"
          className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-night-600 px-4 text-sm font-semibold text-mist-100"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Back to requests
        </Link>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {detailView}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Task Center"
        // on a phone the send form comes first; the explanation is left to the desktop
        intro={
          isMobile
            ? ""
            : "Send a request to the Central Manager. It finds the matching Upazila by keywords, delegates the request to an active agent there and reports back. Replies are marked [Demo]: no AI model is used in this milestone."
        }
      />
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <form onSubmit={handleSubmit} noValidate className="panel space-y-3 p-5" aria-label="Send to Central Manager">
        <h2 className="eyebrow">Send to Central Manager</h2>
        {formError && <ErrorBanner>{formError}</ErrorBanner>}
        <div>
          <label htmlFor="task-title" className="mb-1.5 block text-sm font-medium text-mist-100">
            Request
          </label>
          <input
            id="task-title"
            className="input"
            maxLength={TITLE_MAX}
            placeholder="For example: help me prepare for my exam"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="task-details" className="mb-1.5 block text-sm font-medium text-mist-100">
            Details (optional)
          </label>
          <textarea
            id="task-details"
            className="input min-h-16"
            maxLength={DETAILS_MAX}
            value={details}
            onChange={(event) => setDetails(event.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <label htmlFor="task-priority" className="eyebrow mb-1.5 block">
              Priority
            </label>
            <select id="task-priority" className="input" value={priority} onChange={(event) => setPriority(event.target.value as TaskPriority)}>
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </div>
          <Button type="submit" busy={sending} icon={<Send size={16} aria-hidden="true" />}>
            Send to Central Manager
          </Button>
        </div>
      </form>

      <section className="panel p-5" aria-label="Tasks">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="eyebrow">Requests</h2>
          <p className="font-mono text-[11px] text-mist-500" data-testid="poll-state">
            {active ? "updating automatically…" : "up to date"}
          </p>
        </div>
        {tasks === null ? (
          !error && <p className="mt-3 text-sm text-mist-400">Loading the tasks…</p>
        ) : tasks.length === 0 ? (
          <p className="mt-3 text-sm text-mist-400">No requests yet. Send the first one above.</p>
        ) : (
          <ul className="mt-3 divide-y divide-night-700/70">
            {tasks.map((task) => (
              <li key={task.id}>
                <Link
                  to={`/tasks?id=${task.id}`}
                  aria-current={task.id === selectedId ? "true" : undefined}
                  className={cx(
                    "flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-2 py-2 transition hover:bg-night-800/60",
                    task.id === selectedId && "bg-night-800/80",
                  )}
                >
                  <TaskStatusBadge status={task.status} />
                  <span className="min-w-0 flex-1 truncate text-sm text-mist-50">
                    #{task.id} {task.title}
                  </span>
                  <span className="text-xs text-mist-400">{task.child_count > 0 ? `${task.child_count} delegated` : "not delegated"}</span>
                  <span className="font-mono text-[11px] text-mist-500">{formatTime(task.created_at, timezone)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detailView}
    </div>
  );
}
