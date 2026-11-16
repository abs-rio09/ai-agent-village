import {
  Activity as ActivityIcon,
  Bot,
  Building2,
  CircleCheck,
  CircleX,
  HeartPulse,
  House,
  ListChecks,
  Network,
  RefreshCw,
  ShieldCheck,
  Store,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { api, errorMessage, type ActivityEvent, type Health, type OverviewStats, type Village } from "../api";
import { aiModeLabel, cx } from "../components/ui";
import { usePolling } from "../hooks";

// Village Overview — the control room. Every number and every line on this page comes from the
// backend: GET /api/stats/overview (SQL counts), GET /api/activity/recent (audit log + tasks),
// GET /api/health and GET /api/village. The only local value is the clock.
// The page asks again every 10 seconds, and only while it is visible.

export const POLL_MS = 10_000;
const FEED_LIMIT = 20;

function formatIn(timezone: string, options: Intl.DateTimeFormatOptions, date: Date): string {
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: timezone }).format(date);
  } catch {
    return date.toISOString();
  }
}

function VillageClock({ timezone }: { timezone: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="text-right">
      <p className="font-mono text-3xl tabular-nums tracking-tight text-mist-50">
        {formatIn(timezone, { hour: "2-digit", minute: "2-digit", second: "2-digit" }, now)}
      </p>
      <p className="mt-1 text-xs text-mist-400">
        {formatIn(timezone, { weekday: "long", day: "numeric", month: "long", year: "numeric" }, now)}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- stat tiles

type Tone = "plain" | "river" | "lantern" | "paddy" | "clay";
const TONE_TEXT: Record<Tone, string> = {
  plain: "text-mist-50",
  river: "text-river-300",
  lantern: "text-lantern-300",
  paddy: "text-paddy-300",
  clay: "text-clay-300",
};
const TONE_EDGE: Record<Tone, string> = {
  plain: "before:bg-night-500",
  river: "before:bg-river-400",
  lantern: "before:bg-lantern-400",
  paddy: "before:bg-paddy-400",
  clay: "before:bg-clay-400",
};

interface TileDef {
  key: keyof OverviewStats;
  label: string;
  to: string;
  icon: ReactNode;
  /** The tone the number takes when it is above zero (zero is always quiet). */
  tone: Tone;
  hint?: (stats: OverviewStats) => string;
}

const STRUCTURE: TileDef[] = [
  { key: "upazilas", label: "Upazilas", to: "/upazilas", tone: "plain", icon: <Building2 size={15} aria-hidden="true" /> },
  { key: "unions", label: "Unions", to: "/unions", tone: "plain", icon: <Network size={15} aria-hidden="true" /> },
  { key: "wards", label: "Wards", to: "/wards", tone: "plain", icon: <House size={15} aria-hidden="true" /> },
  {
    key: "offices",
    label: "Offices",
    to: "/wards",
    tone: "plain",
    icon: <Store size={15} aria-hidden="true" />,
    hint: (stats) => `${stats.ward_offices} ward offices + Central Administration`,
  },
];
const AGENTS: TileDef[] = [
  { key: "agents", label: "Agents", to: "/agents", tone: "plain", icon: <Bot size={15} aria-hidden="true" /> },
  {
    key: "active_agents",
    label: "Active agents",
    to: "/agents",
    tone: "paddy",
    icon: <Zap size={15} aria-hidden="true" />,
    hint: () => "can receive tasks; the Central Manager included",
  },
];
const WORK: TileDef[] = [
  { key: "running_tasks", label: "Running tasks", to: "/tasks", tone: "river", icon: <ListChecks size={15} aria-hidden="true" /> },
  {
    key: "pending_approvals",
    label: "Pending approvals",
    to: "/approvals",
    tone: "lantern",
    icon: <ShieldCheck size={15} aria-hidden="true" />,
    hint: (stats) => (stats.pending_approvals > 0 ? "waiting for your decision" : "nothing waits for you"),
  },
  { key: "completed_tasks", label: "Completed tasks", to: "/tasks", tone: "paddy", icon: <CircleCheck size={15} aria-hidden="true" /> },
  { key: "failed_tasks", label: "Failed tasks", to: "/tasks", tone: "clay", icon: <CircleX size={15} aria-hidden="true" /> },
];

function Tile({ tile, stats }: { tile: TileDef; stats: OverviewStats | null }) {
  const value = stats ? stats[tile.key] : null;
  const lit = value !== null && value > 0;
  const tone: Tone = lit ? tile.tone : "plain";
  return (
    <Link
      to={tile.to}
      aria-label={`${tile.label}: ${value ?? "loading"}`}
      className={cx(
        "panel relative block overflow-hidden p-4 pl-5 transition hover:border-night-500 focus-visible:outline-2 focus-visible:outline-lantern-400",
        "before:absolute before:inset-y-3 before:left-0 before:w-[3px] before:rounded-r",
        TONE_EDGE[tone],
      )}
    >
      <div className="flex items-center gap-2 text-mist-400">
        {tile.icon}
        <h3 className="eyebrow">{tile.label}</h3>
      </div>
      <p className="mt-2 flex items-center gap-2">
        <span data-testid={`stat-${tile.key}`} className={cx("font-mono text-3xl tabular-nums tracking-tight", lit ? TONE_TEXT[tone] : "text-mist-50")}>
          {value ?? "—"}
        </span>
        {tile.key === "running_tasks" && lit && <span aria-hidden="true" className="size-2 animate-beacon rounded-full bg-river-400" />}
      </p>
      {tile.hint && stats && <p className="mt-1 text-xs text-mist-400">{tile.hint(stats)}</p>}
    </Link>
  );
}

function TileGroup({ title, tiles, stats, columns }: { title: string; tiles: TileDef[]; stats: OverviewStats | null; columns: string }) {
  return (
    <section aria-label={title} className="min-w-0">
      <h2 className="eyebrow mb-2 flex items-center gap-2">
        <span aria-hidden="true" className="h-px w-5 bg-night-500" />
        {title}
      </h2>
      <div className={cx("grid gap-3", columns)}>
        {tiles.map((tile) => (
          <Tile key={tile.key} tile={tile} stats={stats} />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- recent activity

const DOT: Record<ActivityEvent["tone"], string> = {
  good: "bg-paddy-400",
  bad: "bg-clay-400",
  warn: "bg-lantern-400",
  info: "bg-river-400",
  muted: "bg-night-500",
};

/** "just now", "5 min ago", "3 h ago", then the date. `now` is the browser's clock. */
export function timeAgo(iso: string, now: Date, timezone: string): string {
  const then = new Date(iso);
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  return formatIn(timezone, { day: "numeric", month: "short" }, then);
}

function ActivityFeed({ events, error, timezone }: { events: ActivityEvent[] | null; error: string | null; timezone: string }) {
  const now = new Date();
  return (
    <section className="panel p-5 lg:col-span-2" aria-label="Recent activity">
      <div className="flex items-center gap-2 text-mist-400">
        <ActivityIcon size={15} aria-hidden="true" />
        <h2 className="eyebrow">Recent activity</h2>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-clay-300">
          {error}
        </p>
      )}
      {events === null ? (
        !error && <p className="mt-4 text-sm text-mist-400">Loading…</p>
      ) : events.length === 0 ? (
        <p className="mt-4 text-sm text-mist-400" data-testid="activity-empty">
          Nothing has happened yet. Activity appears here as soon as an agent is created, a request is sent or a decision is made.
        </p>
      ) : (
        <ol className="thin-scroll mt-3 max-h-[34rem] divide-y divide-night-700/70 overflow-y-auto pr-1">
          {events.map((event) => {
            const body = (
              <>
                <span aria-hidden="true" className={cx("mt-1.5 size-2 shrink-0 rounded-full", DOT[event.tone])} />
                <span className="min-w-0 flex-1">
                  <span className="block break-words text-sm text-mist-100">{event.text}</span>
                  <span className="mt-0.5 block text-xs text-mist-500">
                    {event.actor} · <span className="font-mono">{event.action}</span>
                  </span>
                </span>
                <time
                  dateTime={event.time}
                  title={formatIn(timezone, { dateStyle: "medium", timeStyle: "medium" }, new Date(event.time))}
                  className="shrink-0 font-mono text-[11px] text-mist-500"
                >
                  {timeAgo(event.time, now, timezone)}
                </time>
              </>
            );
            return (
              <li key={event.id}>
                {event.link ? (
                  <Link to={event.link} className="-mx-2 flex min-h-11 items-start gap-3 rounded-lg px-2 py-2.5 transition hover:bg-night-800/60">
                    {body}
                  </Link>
                ) : (
                  <div className="flex items-start gap-3 py-2.5">{body}</div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- side column

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-night-700/70 py-2 first:border-t-0">
      <dt className="shrink-0 text-xs text-mist-400">{name}</dt>
      <dd className="min-w-0 break-words text-right font-mono text-[13px] text-mist-100">{children}</dd>
    </div>
  );
}

function HealthCard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await api.health());
      setError(null);
    } catch (cause) {
      setHealth(null);
      setError(cause instanceof Error ? cause.message : "Health check failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const ok = health?.status === "ok";
  return (
    <section className="panel p-5" aria-label="System health">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-mist-400">
          <HeartPulse size={15} aria-hidden="true" />
          <h2 className="eyebrow">System health</h2>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-night-600 px-2.5 py-1 text-xs text-mist-300 transition hover:border-night-500 hover:text-mist-50 disabled:opacity-50 mobile:min-h-11"
        >
          <RefreshCw size={12} aria-hidden="true" className={cx(loading && "animate-spin")} />
          Check again
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-4 text-sm text-clay-300">
          {error}
        </p>
      )}
      {!error && !health && <p className="mt-4 text-sm text-mist-400">Checking…</p>}
      {health && (
        <dl className="mt-3">
          <Row name="Status">
            <span className={cx("inline-flex items-center gap-2", ok ? "text-paddy-300" : "text-clay-300")}>
              <span className={cx("size-2 rounded-full", ok ? "animate-beacon bg-paddy-400" : "bg-clay-400")} aria-hidden="true" />
              <span data-testid="health-status">{health.status}</span>
            </span>
          </Row>
          <Row name="Database">{health.db_ok ? "ok" : "not ok"}</Row>
          <Row name="Journal mode">{health.journal_mode ?? "unknown"}</Row>
          <Row name="Scheduler">{health.scheduler ?? "unknown"}</Row>
          <Row name="Backend version">{health.version}</Row>
        </dl>
      )}
    </section>
  );
}

function aiModeDetail(village: Village): string {
  switch (village.ai_mode) {
    case "demo":
      return "No AI provider and no API key are used. Replies are marked [Demo].";
    case "ollama":
      return `Configured for ${village.ollama_url ?? "a local Ollama server"}. The connection has not been tested.`;
    case "anthropic":
      return village.anthropic_key_configured ? "An API key is saved in data/.env. It has not been tested." : "No API key is saved yet.";
  }
}

function VillageCard({ village }: { village: Village }) {
  return (
    <section className="panel p-5" aria-label="Village">
      <h2 className="eyebrow">Village</h2>
      <dl className="mt-3">
        <Row name="Chairman">{village.chairman_name}</Row>
        <Row name="Timezone">{village.timezone}</Row>
        <Row name="AI mode">{aiModeLabel(village.ai_mode)}</Row>
      </dl>
      <p className="mt-2 text-xs text-mist-400">{aiModeDetail(village)}</p>
    </section>
  );
}

/** Shown while the village has no Upazila: the three steps that bring it to life. */
function StartHere() {
  return (
    <section className="panel border-lantern-500/30 p-5" aria-label="Start here">
      <h2 className="eyebrow !text-lantern-300">Your village is still empty</h2>
      <ol className="mt-3 grid gap-3 text-sm text-mist-300 sm:grid-cols-3">
        <li>
          <span className="font-mono text-xs text-mist-500">1</span>{" "}
          <Link to="/upazilas" className="font-semibold text-lantern-300 underline-offset-4 hover:underline">
            Create Upazilas
          </Link>{" "}
          and generate their standard structure.
        </li>
        <li>
          <span className="font-mono text-xs text-mist-500">2</span>{" "}
          <Link to="/agents/new" className="font-semibold text-lantern-300 underline-offset-4 hover:underline">
            Add an agent
          </Link>{" "}
          to one of the Offices.
        </li>
        <li>
          <span className="font-mono text-xs text-mist-500">3</span>{" "}
          <Link to="/tasks" className="font-semibold text-lantern-300 underline-offset-4 hover:underline">
            Send a request
          </Link>{" "}
          to the Central Manager.
        </li>
      </ol>
    </section>
  );
}

export default function Overview({ village, pollMs = POLL_MS }: { village: Village; pollMs?: number }) {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  usePolling(async () => {
    const [numbers, feed] = await Promise.allSettled([api.statsOverview(), api.recentActivity(FEED_LIMIT)]);
    if (numbers.status === "fulfilled") {
      setStats(numbers.value);
      setStatsError(null);
      setUpdatedAt(new Date());
    } else {
      setStatsError(errorMessage(numbers.reason, "Could not load the village's numbers."));
    }
    if (feed.status === "fulfilled") {
      setEvents(feed.value);
      setFeedError(null);
    } else {
      setFeedError(errorMessage(feed.reason, "Could not load the recent activity."));
    }
  }, pollMs);

  return (
    <div className="space-y-6">
      <section className="panel relative overflow-hidden px-6 py-7 sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-lantern-400/10 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0">
            <p className="eyebrow">Village Overview</p>
            <h1 className="mt-2 truncate text-3xl font-semibold tracking-tight text-mist-50 sm:text-4xl">{village.name}</h1>
            <p className="mt-2 text-sm text-mist-300">
              Chairman <span className="font-medium text-mist-50">{village.chairman_name}</span>
              <span className="mx-2 text-night-500">•</span>
              founded {formatIn(village.timezone, { day: "numeric", month: "long", year: "numeric" }, new Date(village.created_at))}
            </p>
          </div>
          <VillageClock timezone={village.timezone} />
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-mist-400">Counted from the village&apos;s database. Nothing on this page is estimated.</p>
        <p className="font-mono text-[11px] text-mist-500" data-testid="overview-updated">
          {updatedAt
            ? `live · updated ${formatIn(village.timezone, { hour: "2-digit", minute: "2-digit", second: "2-digit" }, updatedAt)}`
            : "loading…"}
        </p>
      </div>
      {statsError && (
        <p role="alert" className="text-sm text-clay-300">
          {statsError}
        </p>
      )}

      {stats !== null && stats.upazilas === 0 && <StartHere />}

      <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
        <TileGroup title="Structure" tiles={STRUCTURE} stats={stats} columns="grid-cols-2 sm:grid-cols-4" />
        <TileGroup title="Agents" tiles={AGENTS} stats={stats} columns="grid-cols-2" />
      </div>
      <TileGroup title="Work" tiles={WORK} stats={stats} columns="grid-cols-2 lg:grid-cols-4" />

      <div className="grid gap-4 lg:grid-cols-3">
        <ActivityFeed events={events} error={feedError} timezone={village.timezone} />
        <div className="space-y-4">
          <HealthCard />
          <VillageCard village={village} />
        </div>
      </div>
    </div>
  );
}
