import { ArrowLeft, List, Map as MapIcon } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError, api, errorMessage, type MapAgent, type MapBuilding, type MapLevel, type MapTarget, type MapView } from "../api";
import MapScene, { agentLabel, buildingLabel } from "../components/map/MapScene";
import { PageHeader } from "../components/org";
import { RobotAvatar, robotRoleFor } from "../components/robots";
import { Button, ErrorBanner, cx } from "../components/ui";
import { useIsMobile, usePolling } from "../hooks";

// Interactive Village Map. ONE level at a time: Village → Upazila → Union → Ward (its Office).
// The level lives in the address (?level=&id=), so Back, reload and a shared link all work, and
// the "List view" shows exactly the same data for keyboard and screen-reader use (?view=list).
// It asks the server again every 10 seconds, and not at all while the tab is hidden.

export const POLL_MS = 10_000;
const LEVELS: MapLevel[] = ["village", "upazila", "union", "ward"];
const LEVEL_NAMES: Record<MapLevel, string> = { village: "Village", upazila: "Upazila", union: "Union", ward: "Ward" };

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function AgentRow({ agent }: { agent: MapAgent }) {
  return (
    <li>
      <Link
        to={`/agents/profile?id=${agent.id}`}
        aria-label={`${agentLabel(agent)} — open profile`}
        className="flex min-h-11 items-center gap-3 rounded-lg px-2 py-1.5 transition hover:bg-night-800/60"
      >
        <RobotAvatar role={robotRoleFor(agent.template_key)} status={agent.activity} taskId={agent.current_task_id} size={40} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-mist-50">{agent.name}</span>
          <span className="block truncate text-xs text-mist-400">
            {agent.role} · {agent.activity}
            {agent.current_task_id ? ` · task #${agent.current_task_id}` : ""}
          </span>
        </span>
      </Link>
    </li>
  );
}

/** The same level as the map, as plain lists: every building and every agent is a link or button. */
function ListView({ view, onOpen }: { view: MapView; onOpen: (target: MapTarget) => void }) {
  const empty = view.buildings.length === 0 && view.agents.length === 0;
  return (
    <section className="panel p-4" aria-label={`List of ${view.name}`} data-testid="map-list">
      {view.level === "ward" && (
        <>
          <h2 className="eyebrow">{view.office_name ?? "Office"}</h2>
          {view.agents.length === 0 ? (
            <p className="mt-3 text-sm text-mist-400">No agent works in this Office yet.</p>
          ) : (
            <ul className="mt-2" aria-label="Agents of this Office">
              {view.agents.map((agent) => (
                <AgentRow key={agent.id} agent={agent} />
              ))}
            </ul>
          )}
        </>
      )}
      {view.level !== "ward" && empty && <p className="text-sm text-mist-400">Nothing here yet.</p>}
      {view.buildings.length > 0 && (
        <ul className="divide-y divide-night-700/70" aria-label="Places">
          {view.buildings.map((building: MapBuilding) => {
            const target = building.target;
            const hidden = building.agent_count - building.agents.length;
            return (
              <li key={`${building.type}-${building.id}`} className="py-3" data-testid={`list-item-${building.type}-${building.id}`}>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {target ? (
                    <button
                      type="button"
                      onClick={() => onOpen(target)}
                      aria-label={`${buildingLabel(building)} — open`}
                      className="min-h-11 rounded-lg px-2 text-left text-sm font-semibold text-lantern-300 underline-offset-4 hover:underline sm:min-h-0 sm:py-1"
                    >
                      {building.name}
                    </button>
                  ) : (
                    <span className="px-2 text-sm font-semibold text-mist-50">{building.name}</span>
                  )}
                  <span className="text-xs text-mist-400">
                    {building.child_count} {building.child_count === 1 ? building.child_label.replace(/s$/, "") : building.child_label}
                    {building.child_label !== "Agents" && <> · {plural(building.agent_count, "agent")}</>} · {plural(building.active_tasks, "active task")}
                  </span>
                </div>
                {building.detail && <p className="px-2 text-xs text-mist-500">{building.detail}</p>}
                {building.agents.length > 0 && (
                  <ul className="mt-1 pl-2" aria-label={`Agents of ${building.name}`}>
                    {building.agents.map((agent) => (
                      <AgentRow key={agent.id} agent={agent} />
                    ))}
                  </ul>
                )}
                {hidden > 0 && <p className="px-2 text-xs text-mist-500">+{hidden} more — open it to see them all</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function VillageMap({ pollMs = POLL_MS }: { pollMs?: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const wanted = searchParams.get("level") as MapLevel | null;
  const level: MapLevel = wanted && LEVELS.includes(wanted) ? wanted : "village";
  const rawId = Number(searchParams.get("id"));
  const id = level !== "village" && Number.isInteger(rawId) && rawId > 0 ? rawId : null;
  const listView = searchParams.get("view") === "list";
  const isMobile = useIsMobile();
  const [view, setView] = useState<MapView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const key = `${level}:${id ?? ""}`;
  const current = useRef(key);
  current.current = key;

  usePolling(
    async () => {
      const asked = key;
      if (level !== "village" && id === null) {
        setMissing(true);
        return;
      }
      try {
        const data = await api.villageMap(level, id);
        if (current.current !== asked) return; // the answer for a level that is no longer shown
        setView(data);
        setError(null);
        setMissing(false);
      } catch (cause) {
        if (current.current !== asked) return;
        if (cause instanceof ApiError && cause.status === 404) setMissing(true);
        else setError(errorMessage(cause, "Could not load the map."));
      }
    },
    pollMs,
    key,
  );

  function go(target: MapTarget) {
    const next: Record<string, string> = {};
    if (target.level !== "village" && target.id !== null) {
      next.level = target.level;
      next.id = String(target.id);
    }
    if (listView) next.view = "list";
    setSearchParams(next);
  }
  function setList(on: boolean) {
    const next = new URLSearchParams(searchParams);
    if (on) next.set("view", "list");
    else next.delete("view");
    setSearchParams(next);
  }

  const shown = view !== null && `${view.level}:${view.id ?? ""}` === key ? view : null;
  const stale = view !== null && shown === null && !missing; // the previous level, until the new one arrives

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Village"
        title="Interactive Village Map"
        intro="Your village as a small town. Open an Upazila to see its Unions, a Union to see its Wards, a Ward to see its Office and the agents at work. Click a robot for the agent's profile."
        actions={
          <div role="group" aria-label="View" className="flex gap-2">
            <Button variant={listView ? "ghost" : "primary"} size="sm" aria-pressed={!listView} icon={<MapIcon size={14} aria-hidden="true" />} onClick={() => setList(false)}>
              Map view
            </Button>
            <Button variant={listView ? "primary" : "ghost"} size="sm" aria-pressed={listView} icon={<List size={14} aria-hidden="true" />} onClick={() => setList(true)}>
              List view
            </Button>
          </div>
        }
      />
      {error && <ErrorBanner>{error}</ErrorBanner>}

      {missing ? (
        <section className="panel px-6 py-10 text-center">
          <h2 className="text-lg font-semibold text-mist-50">This place is not on the map</h2>
          <p className="mt-2 text-sm text-mist-400">It may have been deleted. The village itself is still there.</p>
          <Button className="mt-4" onClick={() => go({ level: "village", id: null })}>
            Back to the village
          </Button>
        </section>
      ) : view === null ? (
        !error && <p className="text-sm text-mist-400">Loading the map…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={view.parent === null}
              icon={<ArrowLeft size={14} aria-hidden="true" />}
              onClick={() => view.parent && go(view.parent)}
            >
              Back
            </Button>
            <nav aria-label="Where you are" className="min-w-0 flex-1">
              <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm">
                {view.breadcrumb.map((crumb, index) => {
                  const last = index === view.breadcrumb.length - 1;
                  return (
                    <li key={`${crumb.level}-${crumb.id ?? "v"}`} className="flex items-center gap-1.5">
                      {index > 0 && (
                        <span aria-hidden="true" className="text-night-500">
                          ›
                        </span>
                      )}
                      {last ? (
                        <span aria-current="page" className="font-semibold text-mist-50">
                          {crumb.label}
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => go({ level: crumb.level, id: crumb.id })}
                          className="rounded px-1 text-lantern-300 underline-offset-4 hover:underline mobile:min-h-11"
                        >
                          {crumb.label}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ol>
            </nav>
            <p className="font-mono text-[11px] text-mist-500" data-testid="map-summary">
              {LEVEL_NAMES[view.level]} · {plural(view.agent_count, "agent")} · {plural(view.active_tasks, "active task")}
              {stale ? " · loading…" : ""}
            </p>
          </div>

          {listView ? (
            <ListView view={view} onOpen={go} />
          ) : (
            <div className={cx("panel overflow-hidden p-1.5", stale && "opacity-60")}>
              <MapScene view={view} portrait={isMobile} onOpen={go} />
            </div>
          )}

          <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-mist-400" aria-label="Legend">
            {(
              [
                ["bg-river-400", "working"],
                ["bg-paddy-400", "idle"],
                ["bg-lantern-400", "waiting for your approval"],
                ["bg-night-500", "offline"],
              ] as const
            ).map(([dot, text]) => (
              <li key={text} className="flex items-center gap-1.5">
                <span aria-hidden="true" className={cx("size-2 rounded-full", dot)} />
                {text}
              </li>
            ))}
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="grid size-4 place-items-center rounded-full bg-river-400 font-mono text-[9px] font-bold text-night-950">
                n
              </span>
              active tasks of a building
            </li>
          </ul>
        </>
      )}
    </div>
  );
}
