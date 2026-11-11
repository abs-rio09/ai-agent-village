import { LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import type { User, Village } from "../api";
import { NAV_GROUPS, findPage } from "../nav";
import { useSession } from "../session";
import { AiModeBadge, VillageCrest, cx } from "./ui";

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Village pages" className="thin-scroll flex h-full flex-col gap-4 overflow-y-auto px-3 pb-6 pt-3">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="eyebrow px-3 pb-1.5">{group.label}</p>
          <ul className="space-y-0.5">
            {group.pages.map((page) => {
              const Icon = page.icon;
              return (
                <li key={page.id}>
                  <NavLink
                    to={page.path}
                    end
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cx(
                        "group flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] transition",
                        isActive
                          ? "bg-night-700/80 text-mist-50 shadow-[inset_2px_0_0_var(--color-lantern-400)]"
                          : "text-mist-300 hover:bg-night-800 hover:text-mist-50",
                      )
                    }
                  >
                    <Icon size={15} aria-hidden="true" className="shrink-0 opacity-80" />
                    <span className="min-w-0 flex-1 leading-snug">{page.label}</span>
                    {page.milestone > 1 && (
                      <span
                        className="rounded border border-night-600 px-1 font-mono text-[10px] text-mist-500"
                        title={`Coming in M${page.milestone}`}
                      >
                        M{page.milestone}
                      </span>
                    )}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 py-4">
      <VillageCrest />
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-wide text-mist-50">AI Agent Village</p>
        <p className="eyebrow !text-[10px]">Control center</p>
      </div>
    </div>
  );
}

export default function AppShell({ user, village }: { user: User; village: Village }) {
  const { logout } = useSession();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const page = findPage(location.pathname);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await logout();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : "Logout failed");
      setLoggingOut(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-[17.5rem] shrink-0 flex-col border-r border-night-700 bg-night-900/80 backdrop-blur lg:flex">
        <Brand />
        <Sidebar />
      </aside>

      {/* small-screen drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/60"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="relative flex h-full w-72 flex-col border-r border-night-700 bg-night-900">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button
                type="button"
                aria-label="Close menu"
                className="rounded-lg p-2 text-mist-300 hover:bg-night-800"
                onClick={() => setMenuOpen(false)}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-night-700 bg-night-950/80 px-4 backdrop-blur sm:px-6">
          <button
            type="button"
            aria-label="Open menu"
            className="rounded-lg p-2 text-mist-300 hover:bg-night-800 lg:hidden"
            onClick={() => setMenuOpen(true)}
          >
            <Menu size={18} aria-hidden="true" />
          </button>

          <div className="min-w-0 flex-1">
            <p className="eyebrow !text-[10px]">Village</p>
            <p data-testid="village-name" className="truncate text-[15px] font-semibold text-mist-50">
              {village.name}
            </p>
          </div>

          <AiModeBadge mode={village.ai_mode} />

          <div className="hidden text-right leading-tight sm:block">
            <p className="eyebrow !text-[10px]">Signed in</p>
            <p className="text-sm text-mist-100">{user.username}</p>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="inline-flex items-center gap-2 rounded-lg border border-night-600 px-3 py-2 text-sm text-mist-100 transition hover:border-clay-400/60 hover:text-clay-300 disabled:opacity-50"
          >
            <LogOut size={15} aria-hidden="true" />
            Log out
          </button>
        </header>

        {logoutError && (
          <p role="alert" className="border-b border-clay-500/40 bg-clay-500/10 px-6 py-2 text-sm text-clay-300">
            Could not log out: {logoutError}
          </p>
        )}

        <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8" aria-label={page?.label ?? "Page"}>
          <div key={location.pathname} className="mx-auto w-full max-w-6xl animate-rise">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
