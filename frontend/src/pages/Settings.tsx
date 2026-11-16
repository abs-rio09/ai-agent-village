import { LogOut, MonitorSmartphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, type DeviceSession } from "../api";
import { formatTime } from "../components/agents";
import { PageHeader, plural } from "../components/org";
import { Button, ErrorBanner } from "../components/ui";

// Application Settings. Only "Devices & sessions" exists so far (built for the installable app,
// DEV-APP-01); the other settings of this page arrive in M8 and are not faked here.

function DevicesAndSessions({ timezone }: { timezone?: string }) {
  const [sessions, setSessions] = useState<DeviceSession[] | null>(null);
  const [error, setError] = useState<string | null>(null); // loading the list
  const [actionError, setActionError] = useState<string | null>(null); // a revoke that failed
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | "others" | null>(null);

  const reload = useCallback(async () => {
    try {
      setSessions(await api.sessions());
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the devices."));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function run(target: number | "others", action: () => Promise<{ revoked: number }>, done: (count: number) => string) {
    setBusy(target);
    setActionError(null);
    setNotice(null);
    try {
      const result = await action();
      setNotice(done(result.revoked));
    } catch (cause) {
      setActionError(errorMessage(cause, "The device could not be logged out."));
    } finally {
      await reload(); // show what the server really has, also after a failure
      setBusy(null);
    }
  }

  const others = (sessions ?? []).filter((session) => !session.current);
  return (
    <section className="panel space-y-4 p-5" aria-label="Devices & sessions">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-mist-50">
            <MonitorSmartphone size={18} aria-hidden="true" className="text-river-300" />
            Devices &amp; sessions
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-mist-400">
            Every browser or installed app that is logged in to the village right now. Revoke a device you no longer use
            or have lost: it is logged out at once.
          </p>
        </div>
        <Button
          variant="danger"
          size="sm"
          disabled={others.length === 0}
          busy={busy === "others"}
          icon={<LogOut size={14} aria-hidden="true" />}
          onClick={() =>
            void run(
              "others",
              () => api.revokeOtherSessions(),
              (count) => `Logged out ${plural(count, "other device")}.`,
            )
          }
        >
          Log out all other devices
        </Button>
      </div>

      {(actionError || error) && <ErrorBanner>{actionError ?? error}</ErrorBanner>}
      {notice && (
        <p role="status" className="text-sm text-paddy-300">
          {notice}
        </p>
      )}

      {sessions === null ? (
        !error && <p className="text-sm text-mist-400">Loading the devices…</p>
      ) : (
        <ul className="divide-y divide-night-700/70" aria-label="Logged-in devices">
          {sessions.map((session) => (
            <li key={session.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3" aria-label={session.device}>
              {/* basis: on a narrow screen the button or note wraps below instead of squeezing the name */}
              <div className="min-w-0 flex-1 basis-60">
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-mist-50">
                  {session.device}
                  {session.current && (
                    <span className="rounded-full border border-paddy-500/40 bg-paddy-500/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-paddy-300">
                      This device
                    </span>
                  )}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-mist-500">
                  logged in {formatTime(session.created_at, timezone)} · last seen {formatTime(session.last_seen_at, timezone)}
                </p>
              </div>
              {session.current ? (
                <p className="text-xs text-mist-400">Use “Log out” at the top to end this one.</p>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  busy={busy === session.id}
                  disabled={busy !== null}
                  aria-label={`Revoke ${session.device}`}
                  onClick={() =>
                    void run(
                      session.id,
                      () => api.revokeSession(session.id),
                      () => `Logged out ${session.device}.`,
                    )
                  }
                >
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-mist-500">
        The device name comes from the browser at login (for example “Chrome on Android”). “Last seen” is updated about
        once a minute while a device is in use. A session ends by itself after 7 days.
      </p>
    </section>
  );
}

export default function SettingsPage({ timezone }: { timezone?: string }) {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="System"
        title="Application Settings"
        intro="Which devices are logged in to your village. The other settings of this page — village name, timezone and password — are not built yet (coming in M8)."
      />
      <DevicesAndSessions timezone={timezone} />
    </div>
  );
}
