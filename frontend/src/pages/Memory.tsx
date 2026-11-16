import { Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { api, errorMessage, type Agent, type MemoryEntry, type MemoryScope, type OrgTree } from "../api";
import { formatTime } from "../components/agents";
import { Dialog } from "../components/Dialog";
import { EmptyState, PageHeader } from "../components/org";
import { Button, ErrorBanner, cx } from "../components/ui";

// Memory & Knowledge Center: the three memory scopes. The Chairman can read, add, edit and delete
// every memory here. What an AGENT may read or write is decided on the server (its permissions
// and its own Upazila) — this page only shows and sends.

const TITLE_MAX = 120;
const CONTENT_MAX = 4000;

const SCOPES: Array<{ value: MemoryScope; label: string; who: string }> = [
  { value: "VILLAGE", label: "Village", who: "Shared with the whole village. Agents read it only with the permission “Read village memory”." },
  { value: "UPAZILA", label: "Upazila", who: "Knowledge of one Upazila. Only agents working in that Upazila can read it." },
  { value: "AGENT", label: "Agent", who: "One agent's own notes. No other agent can read them." },
];

function author(value: string, entry: MemoryEntry): string {
  if (value.startsWith("chairman:")) return `Chairman (${value.slice("chairman:".length)})`;
  if (value.startsWith("agent:")) return value === `agent:${entry.agent_id}` && entry.agent_name ? entry.agent_name : `Agent #${value.slice("agent:".length)}`;
  return value;
}

interface EditorProps {
  scope: MemoryScope;
  entry: MemoryEntry | null; // null = a new memory
  tree: OrgTree | null;
  agents: Agent[];
  onSaved: () => Promise<void>;
  onClose: () => void;
}

function MemoryEditor({ scope, entry, tree, agents, onSaved, onClose }: EditorProps) {
  const [title, setTitle] = useState(entry?.title ?? "");
  const [content, setContent] = useState(entry?.content ?? "");
  const [customer, setCustomer] = useState(entry?.contains_customer_data ?? false);
  const [upazilaId, setUpazilaId] = useState<number | "">(entry?.upazila_id ?? tree?.upazilas[0]?.id ?? "");
  const [agentId, setAgentId] = useState<number | "">(entry?.agent_id ?? agents[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !content.trim()) {
      setError("A memory needs a title and a text.");
      return;
    }
    if (!entry && scope === "UPAZILA" && upazilaId === "") {
      setError("Choose the Upazila this memory belongs to.");
      return;
    }
    if (!entry && scope === "AGENT" && agentId === "") {
      setError("Choose the agent this memory belongs to.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (entry) {
        await api.updateMemory(entry.id, { title: title.trim(), content: content.trim(), contains_customer_data: customer });
      } else {
        await api.createMemory({
          scope,
          upazila_id: scope === "UPAZILA" ? Number(upazilaId) : null,
          agent_id: scope === "AGENT" ? Number(agentId) : null,
          title: title.trim(),
          content: content.trim(),
          contains_customer_data: customer,
        });
      }
      await onSaved();
      onClose();
    } catch (cause) {
      // for example 422: customer data cannot be stored in Village memory
      setError(errorMessage(cause, "The memory could not be saved."));
      setBusy(false);
    }
  }

  const scopeLabel = SCOPES.find((item) => item.value === scope)?.label ?? scope;
  return (
    <Dialog title={entry ? "Memory" : `New ${scopeLabel} memory`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {entry ? (
          <p className="text-xs text-mist-400">
            {scopeLabel} memory
            {entry.upazila_name && <> · {entry.upazila_name}</>}
            {entry.agent_name && <> · {entry.agent_name}</>} · written by {author(entry.created_by, entry)}
          </p>
        ) : scope === "UPAZILA" ? (
          <div>
            <label htmlFor="memory-upazila" className="mb-1.5 block text-sm font-medium text-mist-100">
              Upazila
            </label>
            <select id="memory-upazila" className="input" value={upazilaId} onChange={(event) => setUpazilaId(Number(event.target.value))}>
              {(tree?.upazilas ?? []).length === 0 && <option value="">No Upazila yet</option>}
              {(tree?.upazilas ?? []).map((upazila) => (
                <option key={upazila.id} value={upazila.id}>
                  {upazila.name}
                </option>
              ))}
            </select>
          </div>
        ) : scope === "AGENT" ? (
          <div>
            <label htmlFor="memory-agent" className="mb-1.5 block text-sm font-medium text-mist-100">
              Agent
            </label>
            <select id="memory-agent" className="input" value={agentId} onChange={(event) => setAgentId(Number(event.target.value))}>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.display_name} ({agent.role})
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div>
          <label htmlFor="memory-title" className="mb-1.5 block text-sm font-medium text-mist-100">
            Title
          </label>
          <input id="memory-title" data-autofocus className="input" maxLength={TITLE_MAX} value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div>
          <label htmlFor="memory-content" className="mb-1.5 block text-sm font-medium text-mist-100">
            Text
          </label>
          <textarea
            id="memory-content"
            className="input min-h-40"
            maxLength={CONTENT_MAX}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </div>
        {scope === "VILLAGE" ? (
          <p className="text-xs text-mist-400">
            Village memory is shared, so it must not contain customer data (names with phone numbers, e-mail addresses, orders of a
            person). The server refuses it.
          </p>
        ) : (
          <label className="flex cursor-pointer items-start gap-2.5 text-sm text-mist-100">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-[var(--color-lantern-400)]"
              checked={customer}
              onChange={(event) => setCustomer(event.target.checked)}
            />
            <span>
              Contains customer data
              <span className="block text-xs text-mist-400">The server also marks a text that holds a phone number or an e-mail address.</span>
            </span>
          </label>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy}>
            {entry ? "Save changes" : "Add memory"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ConfirmDelete({ entry, onDone, onClose }: { entry: MemoryEntry; onDone: () => Promise<void>; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteMemory(entry.id);
      await onDone();
      onClose();
    } catch (cause) {
      setError(errorMessage(cause, "The memory could not be deleted."));
      setBusy(false);
    }
  }
  return (
    <Dialog title="Delete this memory?" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-mist-300">
          <strong className="font-semibold text-mist-50">{entry.title}</strong> is removed for good. The deletion is written to the
          audit log; the text is not.
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" busy={busy} data-autofocus onClick={() => void remove()}>
            Delete memory
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export default function Memory({ timezone }: { timezone?: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const scope = (SCOPES.find((item) => item.value === searchParams.get("scope"))?.value ?? "VILLAGE") as MemoryScope;
  const ownerId = Number(searchParams.get("owner")) || null;
  const [entries, setEntries] = useState<MemoryEntry[] | null>(null);
  const [tree, setTree] = useState<OrgTree | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<MemoryEntry | "new" | null>(null);
  const [deleting, setDeleting] = useState<MemoryEntry | null>(null);

  const reload = useCallback(async () => {
    try {
      setEntries(
        await api.memory({
          scope,
          upazila_id: scope === "UPAZILA" ? ownerId : null,
          agent_id: scope === "AGENT" ? ownerId : null,
        }),
      );
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the memories."));
    }
  }, [scope, ownerId]);

  useEffect(() => {
    setEntries(null);
    void reload();
  }, [reload]);

  // the owners for the filter and for a new memory (not needed for Village memory)
  useEffect(() => {
    if (scope === "UPAZILA" && tree === null) void api.orgTree().then(setTree).catch(() => undefined);
    if (scope === "AGENT" && agents.length === 0) void api.agents().then(setAgents).catch(() => undefined);
  }, [scope, tree, agents.length]);

  const info = SCOPES.find((item) => item.value === scope)!;
  const owners: Array<{ id: number; name: string }> =
    scope === "UPAZILA"
      ? (tree?.upazilas ?? []).map((upazila) => ({ id: upazila.id, name: upazila.name }))
      : scope === "AGENT"
        ? agents.map((agent) => ({ id: agent.id, name: agent.display_name }))
        : [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Knowledge"
        title="Memory & Knowledge Center"
        intro="What the village remembers, in three scopes. You can read, add, edit and delete every memory. Agents only reach the scopes their permissions and their own Upazila allow."
        actions={
          <Button icon={<Plus size={16} aria-hidden="true" />} onClick={() => setEditing("new")}>
            Add memory
          </Button>
        }
      />
      <p role="note" className="rounded-xl border border-night-600 bg-night-900/60 px-4 py-3 text-sm text-mist-300">
        Customer data never goes into Village memory — the server refuses it. A task&apos;s temporary working notes are not listed
        here: they are deleted when the task ends. Documents and knowledge search arrive in M6.
      </p>
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div role="tablist" aria-label="Memory scope" className="flex flex-wrap gap-2">
        {SCOPES.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={scope === item.value}
            onClick={() => setSearchParams(item.value === "VILLAGE" ? {} : { scope: item.value })}
            className={cx(
              "min-h-11 rounded-xl border px-4 text-sm font-medium transition sm:min-h-9",
              scope === item.value
                ? "border-lantern-400/60 bg-lantern-500/10 text-lantern-200"
                : "border-night-600 text-mist-300 hover:border-night-500 hover:text-mist-50",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-mist-400">{info.who}</p>
        {scope !== "VILLAGE" && (
          <div>
            <label htmlFor="memory-owner" className="eyebrow mb-1.5 block">
              {scope === "UPAZILA" ? "Upazila" : "Agent"}
            </label>
            <select
              id="memory-owner"
              className="input"
              value={ownerId ?? ""}
              onChange={(event) => setSearchParams(event.target.value ? { scope, owner: event.target.value } : { scope })}
            >
              <option value="">All</option>
              {owners.map((owner) => (
                <option key={owner.id} value={owner.id}>
                  {owner.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {entries === null ? (
        !error && <p className="text-sm text-mist-400">Loading the memories…</p>
      ) : entries.length === 0 ? (
        <EmptyState title={`No ${info.label} memory yet`}>
          <p>Add one here, or let an agent with the tool “Write memory” save a note.</p>
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {entries.map((entry) => (
            <li key={entry.id} className="panel flex min-w-0 flex-col gap-2 p-4" aria-label={`Memory ${entry.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h2 className="min-w-0 break-words text-sm font-semibold text-mist-50">{entry.title}</h2>
                {entry.contains_customer_data && (
                  <span className="rounded border border-clay-500/40 px-1 font-mono text-[10px] uppercase tracking-wider text-clay-300">
                    customer data
                  </span>
                )}
              </div>
              <p className="line-clamp-4 whitespace-pre-wrap break-words text-sm text-mist-300">{entry.content}</p>
              <p className="mt-auto text-xs text-mist-500">
                {entry.upazila_name ?? entry.agent_name ?? "Whole village"} · by {author(entry.updated_by, entry)} ·{" "}
                {formatTime(entry.updated_at, timezone)}
              </p>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" icon={<Pencil size={14} aria-hidden="true" />} onClick={() => setEditing(entry)}>
                  View / edit
                </Button>
                <Button variant="danger" size="sm" icon={<Trash2 size={14} aria-hidden="true" />} onClick={() => setDeleting(entry)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <MemoryEditor
          scope={editing === "new" ? scope : editing.scope}
          entry={editing === "new" ? null : editing}
          tree={tree}
          agents={agents}
          onSaved={reload}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && <ConfirmDelete entry={deleting} onDone={reload} onClose={() => setDeleting(null)} />}
    </div>
  );
}
