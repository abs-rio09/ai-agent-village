import { Bot, Ellipsis, LayoutDashboard, ListChecks, LogOut, Menu, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import type { User, Village } from "../api";
import { useIsMobile } from "../hooks";
import { NAV_GROUPS, findPage, isBuilt } from "../nav";
import { useSession } from "../session";
import { ConnectionIndicator } from "./pwa";
import { AiModeBadge, VillageCrest, cx } from "./ui";

/** The full page list. `touch` makes every row a 44 px touch target (the phone's "More" sheet). */
function Sidebar({ onNavigate, touch = false }: { onNavigate?: () => void; touch?: boolean }) {
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
                        "group flex items-center gap-2.5 rounded-lg px-3 py-1.5 transition",
                        touch ? "min-h-11 text-sm" : "text-[13px]",
                        isActive
                          ? "bg-night-700/80 text-mist-50 shadow-[inset_2px_0_0_var(--color-lantern-400)]"
                          : "text-mist-300 hover:bg-night-800 hover:text-mist-50",
                      )
                    }
                  >
                    <Icon size={15} aria-hidden="true" className="shrink-0 opacity-80" />
                    <span className="min-w-0 flex-1 leading-snug">{page.label}</span>
                    {!isBuilt(page) && (
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

// The phone's bottom bar: the three pages used most, plus "More" for everything else.
const BOTTOM_ITEMS: Array<{ to: string; label: string; icon: LucideIcon; end?: boolean }> = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/agents", label: "Agents", icon: Bot },
];

const BOTTOM_ITEM =
  "flex min-h-14 w-full flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium transition";

function BottomNav({ moreOpen, onMore }: { moreOpen: boolean; onMore: () => void }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-night-700 bg-night-900/95 pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] backdrop-blur"
    >
      <ul className="grid grid-cols-4">
        {BOTTOM_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) => cx(BOTTOM_ITEM, isActive && !moreOpen ? "text-lantern-300" : "text-mist-400")}
              >
                <Icon size={20} aria-hidden="true" />
                {item.label}
              </NavLink>
            </li>
          );
        })}
        <li>
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={moreOpen}
            onClick={onMore}
            className={cx(BOTTOM_ITEM, moreOpen ? "text-lantern-300" : "text-mist-400")}
          >
            <Ellipsis size={20} aria-hidden="true" />
            More
          </button>
        </li>
      </ul>
    </nav>
  );
}

/** The full menu as a sheet that slides over the page from the bottom (phones only). */
function MoreSheet({ user, village, onClose }: { user: User; village: Village; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.focus();
  }, []);
  return (
    <div className="fixed inset-0 z-40" onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <button type="button" aria-label="Close menu" tabIndex={-1} className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="All pages"
        tabIndex={-1}
        className="absolute inset-x-0 bottom-0 flex max-h-[88vh] flex-col rounded-t-2xl border-t border-night-600 bg-night-900 pb-[env(safe-area-inset-bottom)] outline-none"
      >
        <div className="flex items-center justify-between border-b border-night-700 py-1 pl-5 pr-2">
          <p className="text-sm font-semibold text-mist-50">All pages</p>
          <button
            type="button"
            aria-label="Close menu"
            onClick={onClose}
            className="grid size-11 place-items-center rounded-lg text-mist-300 hover:bg-night-800"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Sidebar touch onNavigate={onClose} />
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-night-700 px-5 py-3">
          <p className="min-w-0 truncate text-xs text-mist-400">
            Signed in as <span className="text-mist-100">{user.username}</span>
          </p>
          <AiModeBadge mode={village.ai_mode} />
        </div>
      </div>
    </div>
  );
}

export default function AppShell({ user, village }: { user: User; village: Village }) {
  const { logout } = useSession();
  const location = useLocation();
  const isMobile = useIsMobile();
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
      {!isMobile && (
        <aside className="sticky top-0 hidden h-screen w-[17.5rem] shrink-0 flex-col border-r border-night-700 bg-night-900/80 backdrop-blur lg:flex">
          <Brand />
          <Sidebar />
        </aside>
      )}

      {/* phones: bottom navigation; "More" opens the full menu as a sheet */}
      {isMobile && <BottomNav moreOpen={menuOpen} onMore={() => setMenuOpen((open) => !open)} />}
      {isMobile && menuOpen && <MoreSheet user={user} village={village} onClose={() => setMenuOpen(false)} />}

      {/* tablets and narrow desktop windows: drawer */}
      {!isMobile && menuOpen && (
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
        <header className="sticky top-0 z-30 flex min-h-16 items-center gap-4 border-b border-night-700 bg-night-950/80 px-4 pt-[env(safe-area-inset-top)] backdrop-blur mobile:gap-2.5 sm:px-6">
          {!isMobile && (
            <button
              type="button"
              aria-label="Open menu"
              className="rounded-lg p-2 text-mist-300 hover:bg-night-800 lg:hidden"
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={18} aria-hidden="true" />
            </button>
          )}

          <div className="min-w-0 flex-1">
            <p className="eyebrow !text-[10px]">Village</p>
            <p data-testid="village-name" className="truncate text-[15px] font-semibold text-mist-50">
              {village.name}
            </p>
          </div>

          <ConnectionIndicator />
          {!isMobile && <AiModeBadge mode={village.ai_mode} />}

          <div className="hidden text-right leading-tight sm:block">
            <p className="eyebrow !text-[10px]">Signed in</p>
            <p className="text-sm text-mist-100">{user.username}</p>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-night-600 px-3 py-2 text-sm text-mist-100 transition hover:border-clay-400/60 hover:text-clay-300 disabled:opacity-50 mobile:size-11 mobile:px-0"
          >
            <LogOut size={15} aria-hidden="true" />
            <span className="mobile:sr-only">Log out</span>
          </button>
        </header>

        {logoutError && (
          <p role="alert" className="border-b border-clay-500/40 bg-clay-500/10 px-6 py-2 text-sm text-clay-300">
            Could not log out: {logoutError}
          </p>
        )}

        <main
          className="flex-1 px-4 py-6 mobile:pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-8"
          aria-label={page?.label ?? "Page"}
        >
          <div key={location.pathname} className="mx-auto w-full max-w-6xl animate-rise">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
