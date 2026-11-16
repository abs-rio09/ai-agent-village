import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage, type Agent } from "../api";
import { LifecycleBadge, RuntimeBadge } from "../components/agents";
import { RobotAvatar, robotRoleFor } from "../components/robots";
import { EmptyState, PageHeader, plural, useOrgTree } from "../components/org";
import { ErrorBanner } from "../components/ui";

// Agent Management: every agent as a card, filtered by Upazila. Everything shown comes from
// GET /api/agents; an agent's Upazila, Union and Ward are derived from its office by the server.

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <Link
      to={`/agents/profile?id=${agent.id}`}
      aria-label={`${agent.display_name}, ${agent.role}`}
      className="panel flex min-w-0 gap-4 p-4 transition hover:border-night-500"
    >
      <RobotAvatar
        role={robotRoleFor(agent.template_key)}
        status={agent.activity}
        taskId={agent.current_task_id}
        name={agent.display_name}
        title={agent.role}
        size={56}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="truncate text-[15px] font-semibold text-mist-50">{agent.display_name}</h2>
          {agent.is_central_manager && (
            <span className="rounded border border-lantern-500/40 px-1.5 font-mono text-[10px] uppercase tracking-wider text-lantern-200">
              Central Manager
            </span>
          )}
        </div>
        <p className="text-sm text-mist-300">{agent.role}</p>
        <p className="mt-1 truncate text-xs text-mist-400" title={agent.location?.path}>
          {agent.location ? agent.location.path : "No office — its office was deleted"}
        </p>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <LifecycleBadge lifecycle={agent.lifecycle} />
          <RuntimeBadge state={agent.activity} />
        </div>
      </div>
    </Link>
  );
}

export default function Agents() {
  const { tree, error: treeError } = useOrgTree();
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const upazilaId = Number(searchParams.get("upazila")) || null;

  useEffect(() => {
    let cancelled = false;
    api
      .agents({ upazila_id: upazilaId })
      .then((value) => {
        if (cancelled) return;
        setAgents(value);
        setError(null);
      })
      .catch((cause: unknown) => !cancelled && setError(errorMessage(cause, "Could not load the agents.")));
    return () => {
      cancelled = true;
    };
  }, [upazilaId]);

  const upazilas = tree?.upazilas ?? [];
  const filterName = upazilas.find((item) => item.id === upazilaId)?.name;
  const newAgentLink = upazilaId ? `/agents/new?upazila=${upazilaId}` : "/agents/new";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agents"
        title="Agent Management"
        intro="Agents work in an Office. Create one from a template, then activate, pause or disable it. In this milestone every agent answers with the Demo provider — no AI model is used."
        actions={
          <Link
            to={newAgentLink}
            className="inline-flex items-center gap-2 rounded-xl bg-lantern-400 px-4 py-2.5 text-sm font-semibold text-night-950 shadow-[0_8px_24px_-10px_rgb(246_181_69/0.7)] transition hover:bg-lantern-300"
          >
            <Plus size={16} aria-hidden="true" />
            New agent
          </Link>
        }
      />
      {(error || treeError) && <ErrorBanner>{error ?? treeError}</ErrorBanner>}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-56 sm:max-w-xs">
          <label htmlFor="agents-upazila" className="eyebrow mb-1.5 block">
            Show agents of
          </label>
          <select
            id="agents-upazila"
            className="input"
            value={upazilaId ?? ""}
            onChange={(event) => setSearchParams(event.target.value ? { upazila: event.target.value } : {})}
          >
            <option value="">The whole village</option>
            {upazilas.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        {agents && (
          <p className="text-sm text-mist-400" data-testid="agent-count">
            {plural(agents.length, "agent")}
            {filterName ? ` in ${filterName}` : ""}
          </p>
        )}
      </div>

      {!agents ? (
        !error && <p className="text-sm text-mist-400">Loading the agents…</p>
      ) : agents.length === 0 ? (
        <EmptyState title={filterName ? `${filterName} has no agents yet` : "No agents yet"}>
          <p>The Central Manager can only delegate a request to an active agent inside the matching Upazila.</p>
          <Link to={newAgentLink} className="font-medium text-lantern-300 underline-offset-4 hover:underline">
            Create an agent
          </Link>
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" role="group" aria-label="Agents">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
