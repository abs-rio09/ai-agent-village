import { CirclePause, CirclePlay, CircleSlash, Save, Trash } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, errorMessage, type Agent, type AgentAction, type AgentOptions, type AgentPatch, type OrgTree, type Task } from "../api";
import {
  AgentAvatar,
  CatalogChecklist,
  EnforcementNote,
  INSTRUCTIONS_MAX,
  LifecycleBadge,
  OfficePicker,
  RuntimeBadge,
  TaskStatusBadge,
  formatTime,
} from "../components/agents";
import { ConfirmDeleteDialog } from "../components/Dialog";
import { Breadcrumbs, DESCRIPTION_MAX, EmptyState, NAME_MAX, PageHeader, Picker, useOrgTree, validateName } from "../components/org";
import { Button, ErrorBanner, Field } from "../components/ui";

// Agent Profile: one agent's settings, lifecycle buttons, safe deletion and task history.
// `?id=` picks the agent; without it the first agent (the Central Manager) is shown.

function same(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

interface EditorProps {
  agent: Agent;
  tree: OrgTree;
  options: AgentOptions;
  onSaved: () => Promise<void>;
}

function AgentEditor({ agent, tree, options, onSaved }: EditorProps) {
  const [name, setName] = useState(agent.display_name);
  const [role, setRole] = useState(agent.role);
  const [description, setDescription] = useState(agent.description);
  const [instructions, setInstructions] = useState(agent.system_instructions);
  const [officeId, setOfficeId] = useState(agent.office_id);
  const [tools, setTools] = useState(agent.allowed_tools);
  const [permissions, setPermissions] = useState(agent.permissions);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const patch: AgentPatch = {};
  if (name.trim() !== agent.display_name) patch.display_name = name.trim();
  if (role.trim() !== agent.role) patch.role = role.trim();
  if (description.trim() !== agent.description) patch.description = description.trim();
  if (instructions.trim() !== agent.system_instructions) patch.system_instructions = instructions.trim();
  if (officeId !== null && officeId !== agent.office_id) patch.office_id = officeId;
  if (!same(tools, agent.allowed_tools)) patch.allowed_tools = tools;
  if (!same(permissions, agent.permissions)) patch.permissions = permissions;
  const dirty = Object.keys(patch).length > 0;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateName(name, "a name for the agent") ?? validateName(role, "a role");
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.updateAgent(agent.id, patch); // only what changed is sent
      setSaved(true);
      await onSaved();
    } catch (cause) {
      setError(errorMessage(cause, "The agent could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  const edited = () => setSaved(false);
  return (
    <form onSubmit={handleSubmit} noValidate className="panel space-y-4 p-5" aria-label="Agent settings">
      <h2 className="eyebrow">Settings</h2>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field id="profile-name" label="Agent name">
          <input
            id="profile-name"
            className="input"
            maxLength={NAME_MAX}
            value={name}
            onChange={(event) => (setName(event.target.value), edited())}
            aria-describedby="profile-name-note"
          />
        </Field>
        <Field id="profile-role" label="Role">
          <input
            id="profile-role"
            className="input"
            maxLength={NAME_MAX}
            value={role}
            onChange={(event) => (setRole(event.target.value), edited())}
            aria-describedby="profile-role-note"
          />
        </Field>
      </div>
      <Field id="profile-description" label="Responsibilities">
        <textarea
          id="profile-description"
          className="input min-h-20"
          maxLength={DESCRIPTION_MAX}
          value={description}
          onChange={(event) => (setDescription(event.target.value), edited())}
          aria-describedby="profile-description-note"
        />
      </Field>
      <Field id="profile-instructions" label="System instructions" hint="The Demo provider does not read them; a real AI provider will.">
        <textarea
          id="profile-instructions"
          className="input min-h-32"
          maxLength={INSTRUCTIONS_MAX}
          value={instructions}
          onChange={(event) => (setInstructions(event.target.value), edited())}
          aria-describedby="profile-instructions-note"
        />
      </Field>

      {agent.is_central_manager ? (
        <p className="text-sm text-mist-400">Office: Central Administration. The Central Manager cannot be moved.</p>
      ) : (
        <fieldset>
          <legend className="mb-1.5 block text-sm font-medium text-mist-100">Office</legend>
          <OfficePicker tree={tree} value={officeId} onChange={(value) => (setOfficeId(value), edited())} idPrefix="profile-office" />
        </fieldset>
      )}

      <EnforcementNote />
      <CatalogChecklist legend="Allowed tools" items={options.tools} selected={tools} onChange={(value) => (setTools(value), edited())} />
      <CatalogChecklist
        legend="Permissions"
        items={options.permissions}
        selected={permissions}
        onChange={(value) => (setPermissions(value), edited())}
      />

      <div className="flex flex-wrap items-center justify-end gap-3">
        {saved && !dirty && (
          <p role="status" className="text-sm text-paddy-300">
            Saved.
          </p>
        )}
        <Button type="submit" disabled={!dirty} busy={busy} icon={<Save size={16} aria-hidden="true" />}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

function TaskHistory({ tasks, timezone }: { tasks: Task[] | null; timezone?: string }) {
  return (
    <section className="panel p-5" aria-label="Task history">
      <h2 className="eyebrow">Task history</h2>
      {tasks === null ? (
        <p className="mt-3 text-sm text-mist-400">Loading…</p>
      ) : tasks.length === 0 ? (
        <p className="mt-3 text-sm text-mist-400">This agent has not received a task yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-night-700/70">
          {tasks.map((task) => (
            <li key={task.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <TaskStatusBadge status={task.status} />
              <Link
                to={`/tasks?id=${task.parent_task_id ?? task.id}`}
                className="min-w-0 flex-1 truncate text-sm text-mist-100 underline-offset-4 hover:text-lantern-300 hover:underline"
              >
                #{task.id} {task.title}
              </Link>
              <span className="font-mono text-[11px] text-mist-500">{formatTime(task.created_at, timezone)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function AgentProfile({ timezone }: { timezone?: string }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { tree, error: treeError } = useOrgTree();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [options, setOptions] = useState<AgentOptions | null>(null);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<AgentAction | null>(null);
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    try {
      setAgents(await api.agents());
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the agents."));
    }
  }, []);

  useEffect(() => {
    void reload();
    api
      .agentOptions()
      .then(setOptions)
      .catch((cause: unknown) => setError(errorMessage(cause, "Could not load the tool list.")));
  }, [reload]);

  const requested = Number(searchParams.get("id")) || null;
  const agent = agents?.find((item) => item.id === requested) ?? (requested === null ? agents?.[0] : undefined) ?? null;
  const agentId = agent?.id ?? null;

  useEffect(() => {
    if (agentId === null) return;
    let cancelled = false;
    setTasks(null);
    setActionError(null);
    api
      .tasks({ agent_id: agentId })
      .then((value) => !cancelled && setTasks(value))
      .catch((cause: unknown) => !cancelled && setError(errorMessage(cause, "Could not load the task history.")));
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  async function act(action: AgentAction) {
    if (!agent) return;
    setBusyAction(action);
    setActionError(null);
    try {
      await api.agentAction(agent.id, action);
    } catch (cause) {
      setActionError(errorMessage(cause, "The agent could not be changed."));
    } finally {
      await reload();
      setBusyAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Agent Management", to: "/agents" }, { label: agent?.display_name ?? "Agent Profile" }]} />
      <PageHeader
        eyebrow="Agents"
        title="Agent Profile"
        intro="One agent's role, Office, instructions, tools and permissions, with its task history. Pause an agent to stop it receiving tasks; disable it to retire it and keep its history."
      />
      {(error || treeError) && <ErrorBanner>{error ?? treeError}</ErrorBanner>}

      {!agents ? (
        !error && <p className="text-sm text-mist-400">Loading the agent…</p>
      ) : !agent ? (
        <EmptyState title="This agent does not exist">
          <p>It may have been deleted.</p>
          <Link to="/agents" className="font-medium text-lantern-300 underline-offset-4 hover:underline">
            Back to Agent Management
          </Link>
        </EmptyState>
      ) : (
        <>
          <Picker id="pick-agent" label="Agent" value={agent.id} options={agents.map((item) => ({ id: item.id, name: item.display_name }))} onChange={(id) => setSearchParams({ id: String(id) })} />

          <section className="panel p-5" aria-label={`Agent ${agent.display_name}`}>
            <div className="flex flex-wrap items-start gap-4">
              <AgentAvatar avatarKey={agent.avatar_key} size={72} />
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-xl font-semibold text-mist-50">{agent.display_name}</h2>
                <p className="text-sm text-mist-300">
                  {agent.role}
                  {agent.template_name ? <span className="text-mist-500"> · template: {agent.template_name}</span> : null}
                </p>
                <p className="mt-1 text-sm text-mist-400">{agent.location ? agent.location.path : "No office — its office was deleted"}</p>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <LifecycleBadge lifecycle={agent.lifecycle} />
                  <RuntimeBadge state={agent.runtime_state} />
                  <span className="font-mono text-[11px] text-mist-500">provider: {agent.provider}</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {agent.is_central_manager ? (
                  <p className="max-w-xs text-xs text-mist-400">
                    The Central Manager is always active and cannot be paused, disabled or deleted: the village needs it to route tasks.
                  </p>
                ) : (
                  <>
                    {agent.lifecycle !== "active" && (
                      <Button size="sm" busy={busyAction === "activate"} icon={<CirclePlay size={14} aria-hidden="true" />} onClick={() => void act("activate")}>
                        Activate
                      </Button>
                    )}
                    {agent.lifecycle === "active" && (
                      <Button variant="ghost" size="sm" busy={busyAction === "pause"} icon={<CirclePause size={14} aria-hidden="true" />} onClick={() => void act("pause")}>
                        Pause
                      </Button>
                    )}
                    {agent.lifecycle !== "disabled" && (
                      <Button variant="ghost" size="sm" busy={busyAction === "disable"} icon={<CircleSlash size={14} aria-hidden="true" />} onClick={() => void act("disable")}>
                        Disable
                      </Button>
                    )}
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={agent.has_history}
                      title={agent.has_history ? "This agent has task history, so it can only be disabled." : undefined}
                      icon={<Trash size={14} aria-hidden="true" />}
                      onClick={() => setDeleting(true)}
                    >
                      Delete
                    </Button>
                  </>
                )}
              </div>
            </div>
            {agent.has_history && !agent.is_central_manager && (
              <p className="mt-3 text-xs text-mist-400">
                This agent has task history, so it cannot be deleted — disable it instead and its history is kept.
              </p>
            )}
            {agent.location === null && (
              <p className="mt-3 text-xs text-lantern-200">Its Office was deleted. Choose a new Office below and save before activating it.</p>
            )}
            {actionError && (
              <div className="mt-3">
                <ErrorBanner>{actionError}</ErrorBanner>
              </div>
            )}
          </section>

          {tree && options ? (
            <AgentEditor key={`${agent.id}-${agent.updated_at}`} agent={agent} tree={tree} options={options} onSaved={reload} />
          ) : (
            !(error || treeError) && <p className="text-sm text-mist-400">Loading the settings…</p>
          )}

          <TaskHistory tasks={tasks} timezone={timezone} />
        </>
      )}

      {deleting && agent && (
        <ConfirmDeleteDialog
          kind="Agent"
          name={agent.display_name}
          consequence=""
          onConfirm={async () => {
            await api.deleteAgent(agent.id, agent.display_name); // a 409 (history) is shown in the dialog
            setDeleting(false);
            navigate("/agents");
          }}
          onClose={() => setDeleting(false)}
        />
      )}
    </div>
  );
}
