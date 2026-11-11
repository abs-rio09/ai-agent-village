import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { AiMode } from "../api";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** The village mark: a lit house under a signal arc. */
export function VillageCrest({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className="shrink-0">
      <rect width="40" height="40" rx="11" className="fill-night-800 stroke-night-600" strokeWidth="1" />
      <path d="M13 12.5a10 10 0 0 1 14 0" className="stroke-river-400" strokeWidth="1.6" fill="none" strokeLinecap="round" opacity="0.55" />
      <path d="M16 15.5a5.6 5.6 0 0 1 8 0" className="stroke-river-400" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M9 23.5 20 15l11 8.5" className="stroke-lantern-400" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12.5 22.5V31h15v-8.5" className="stroke-paddy-400" strokeWidth="2.1" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="18" y="25" width="4" height="6" rx="1" className="fill-lantern-300" />
    </svg>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
  busy?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", busy = false, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" &&
          "bg-lantern-400 text-night-950 shadow-[0_8px_24px_-10px_rgb(246_181_69/0.7)] hover:bg-lantern-300 active:translate-y-px",
        variant === "ghost" && "border border-night-600 text-mist-100 hover:border-night-500 hover:bg-night-800",
        className,
      )}
    >
      {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}

interface FieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}

/** Label + control + hint/error. The control must use `id` and `aria-describedby={`${id}-note`}`. */
export function Field({ id, label, hint, error, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-mist-100">
        {label}
      </label>
      {children}
      <div id={`${id}-note`} className="min-h-5 text-xs">
        {error ? (
          <p role="alert" className="text-clay-300">
            {error}
          </p>
        ) : (
          hint && <p className="text-mist-500">{hint}</p>
        )}
      </div>
    </div>
  );
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-xl border border-clay-500/40 bg-clay-500/10 px-4 py-3 text-sm text-clay-300">
      {children}
    </div>
  );
}

/** Honest provider label: nothing but Demo has ever been exercised, so say "not tested". */
export function aiModeLabel(mode: AiMode): string {
  switch (mode) {
    case "demo":
      return "Demo";
    case "ollama":
      return "Ollama: not tested";
    case "anthropic":
      return "Anthropic: not tested";
  }
}

export function AiModeBadge({ mode }: { mode: AiMode }) {
  const demo = mode === "demo";
  return (
    <span
      data-testid="ai-mode-badge"
      title={
        demo
          ? "Demo Mode: no AI provider or API key is used."
          : "This provider was configured during setup but its connection has not been tested."
      }
      className={cx(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.12em]",
        demo ? "border-paddy-500/40 bg-paddy-500/10 text-paddy-300" : "border-lantern-500/40 bg-lantern-500/10 text-lantern-200",
      )}
    >
      <span className={cx("size-1.5 rounded-full", demo ? "bg-paddy-400" : "bg-lantern-400")} aria-hidden="true" />
      {aiModeLabel(mode)}
    </span>
  );
}

export function FullScreenMessage({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        <VillageCrest size={48} />
        <h1 className="text-lg font-semibold text-mist-50">{title}</h1>
        {children}
      </div>
    </div>
  );
}
