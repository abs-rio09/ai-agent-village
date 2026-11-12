// Shared pieces of the three organization pages: data hook, breadcrumbs, icons, small helpers.

import {
  BookOpen,
  Briefcase,
  Building2,
  ChevronRight,
  CodeXml,
  FlaskConical,
  GraduationCap,
  Landmark,
  Rocket,
  Store,
  Target,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { api, errorMessage, type OrgTree } from "../api";

export const NAME_MAX = 80;
export const DESCRIPTION_MAX = 500;
export const RESPONSIBILITY_MAX = 200;

/** Client-side copy of the server rule: names are trimmed and 1–80 characters. */
export function validateName(value: string, what = "a name"): string | null {
  const trimmed = value.trim();
  if (!trimmed) return `Enter ${what}.`;
  if (trimmed.length > NAME_MAX) return `Use ${NAME_MAX} characters or fewer.`;
  return null;
}

export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// Icon keys are stored on the server; unknown keys fall back to a building.
const ICONS: Record<string, { label: string; icon: LucideIcon }> = {
  "": { label: "Building (default)", icon: Building2 },
  "graduation-cap": { label: "Study", icon: GraduationCap },
  store: { label: "Shop", icon: Store },
  briefcase: { label: "Career", icon: Briefcase },
  flask: { label: "Research", icon: FlaskConical },
  code: { label: "Code", icon: CodeXml },
  user: { label: "Person", icon: UserRound },
  landmark: { label: "Landmark", icon: Landmark },
  book: { label: "Book", icon: BookOpen },
  target: { label: "Target", icon: Target },
  rocket: { label: "Rocket", icon: Rocket },
  wrench: { label: "Tools", icon: Wrench },
};

export const ICON_OPTIONS = Object.entries(ICONS).map(([key, value]) => ({ key, label: value.label }));

export function OrgIcon({ name, size = 18 }: { name: string; size?: number }) {
  const Icon = ICONS[name]?.icon ?? Building2;
  return <Icon size={size} aria-hidden="true" />;
}

/** Loads GET /api/org/tree once and again after every change. */
export function useOrgTree() {
  const [tree, setTree] = useState<OrgTree | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setTree(await api.orgTree());
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the organization."));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { tree, error, reload };
}

export interface Crumb {
  label: string;
  to?: string;
}

/** Village › Upazila › Union › Ward. The last crumb is the current place. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1.5 text-sm">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={`${index}-${item.label}`} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <ChevronRight size={14} aria-hidden="true" className="shrink-0 text-night-500" />}
              {item.to && !last ? (
                <Link to={item.to} className="truncate text-mist-400 underline-offset-4 hover:text-lantern-300 hover:underline">
                  {item.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className={last ? "truncate font-medium text-mist-50" : "truncate text-mist-400"}>
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function PageHeader({ title, intro, actions }: { title: string; intro: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <p className="eyebrow">Administration</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-mist-50">{title}</h1>
        <p className="mt-1.5 max-w-2xl text-sm text-mist-400">{intro}</p>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="panel px-8 py-12 text-center">
      <h2 className="text-lg font-semibold text-mist-50">{title}</h2>
      {children && <div className="mx-auto mt-3 flex max-w-xl flex-col items-center gap-4 text-sm text-mist-400">{children}</div>}
    </section>
  );
}

/** Labelled <select> used to pick the Upazila / Union a page works on. */
export function Picker({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: number | null;
  options: Array<{ id: number; name: string }>;
  onChange: (id: number) => void;
}) {
  return (
    <div className="min-w-56 flex-1 sm:max-w-xs">
      <label htmlFor={id} className="eyebrow mb-1.5 block">
        {label}
      </label>
      <select
        id={id}
        className="input"
        value={value ?? ""}
        disabled={options.length === 0}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {options.length === 0 && <option value="">None yet</option>}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </div>
  );
}
