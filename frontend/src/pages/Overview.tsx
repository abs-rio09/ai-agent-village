import { Clock, Cpu, HeartPulse, Layers, RefreshCw, User as UserIcon } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api, type Health, type Village } from "../api";
import { aiModeLabel, cx } from "../components/ui";

// M1 overview: every value on this page comes from GET /api/village or GET /api/health
// (plus the browser clock, shown in the village timezone). No statistics exist yet.

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

function Card({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <section className="panel p-5" aria-label={label}>
      <div className="flex items-center gap-2 text-mist-400">
        {icon}
        <h2 className="eyebrow">{label}</h2>
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-night-700/70 py-2 first:border-t-0">
      <dt className="shrink-0 text-xs text-mist-400">{name}</dt>
      <dd className="text-right font-mono text-[13px] text-mist-100">{children}</dd>
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
    <section className="panel p-5 md:col-span-2" aria-label="System health">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-mist-400">
          <HeartPulse size={15} aria-hidden="true" />
          <h2 className="eyebrow">System health</h2>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-night-600 px-2.5 py-1 text-xs text-mist-300 transition hover:border-night-500 hover:text-mist-50 disabled:opacity-50"
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
        <div className="mt-4 grid gap-x-10 sm:grid-cols-2">
          <dl>
            <Row name="Status">
              <span className={cx("inline-flex items-center gap-2", ok ? "text-paddy-300" : "text-clay-300")}>
                <span className={cx("size-2 rounded-full", ok ? "animate-beacon bg-paddy-400" : "bg-clay-400")} aria-hidden="true" />
                <span data-testid="health-status">{health.status}</span>
              </span>
            </Row>
            <Row name="Database">{health.db_ok ? "ok" : "not ok"}</Row>
            <Row name="Journal mode">{health.journal_mode ?? "unknown"}</Row>
          </dl>
          <dl>
            <Row name="Backend version">{health.version}</Row>
            <Row name="Demo Mode">{health.demo_mode ? "on" : "off — key saved, not tested"}</Row>
            <Row name="Setup completed">{health.setup_completed ? "yes" : "no"}</Row>
          </dl>
        </div>
      )}
    </section>
  );
}

function aiModeDetail(village: Village): string {
  switch (village.ai_mode) {
    case "demo":
      return "No AI provider and no API key are used.";
    case "ollama":
      return `Configured for ${village.ollama_url ?? "a local Ollama server"}. The connection has not been tested.`;
    case "anthropic":
      return village.anthropic_key_configured
        ? "An API key is saved in data/.env. It has not been tested."
        : "No API key is saved yet.";
  }
}

export default function Overview({ village }: { village: Village }) {
  return (
    <div className="space-y-6">
      <section className="panel relative overflow-hidden px-6 py-7 sm:px-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-lantern-400/10 blur-3xl"
        />
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

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card icon={<UserIcon size={15} aria-hidden="true" />} label="Chairman">
          <p className="text-lg font-medium text-mist-50">{village.chairman_name}</p>
          <p className="mt-1 text-xs text-mist-400">Owner and only administrator</p>
        </Card>
        <Card icon={<Clock size={15} aria-hidden="true" />} label="Timezone">
          <p className="font-mono text-lg text-mist-50">{village.timezone}</p>
          <p className="mt-1 text-xs text-mist-400">Used for schedules and reports</p>
        </Card>
        <Card icon={<Cpu size={15} aria-hidden="true" />} label="AI mode">
          <p className="text-lg font-medium text-mist-50">{aiModeLabel(village.ai_mode)}</p>
          <p className="mt-1 text-xs text-mist-400">{aiModeDetail(village)}</p>
        </Card>
        <Card icon={<Layers size={15} aria-hidden="true" />} label="Default structure">
          <p className="text-lg font-medium capitalize text-mist-50">{village.default_structure}</p>
          <p className="mt-1 text-xs text-mist-400">Saved choice only — Upazilas, Unions and Wards arrive in M2</p>
        </Card>

        <HealthCard />

        <section className="panel p-5 md:col-span-2" aria-label="What exists today">
          <h2 className="eyebrow">What exists today</h2>
          <p className="mt-3 text-sm leading-relaxed text-mist-300">
            This is milestone 1: the foundation. The village has a secure login, a database and this control
            center. There are no Upazilas, agents or tasks yet, so there are no statistics to show — the pages
            in the sidebar marked <span className="font-mono text-xs text-mist-100">M2</span>–
            <span className="font-mono text-xs text-mist-100">M8</span> are built in later milestones.
          </p>
        </section>
      </div>
    </div>
  );
}
