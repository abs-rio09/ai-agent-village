import type { ReactNode } from "react";

import { cx } from "../ui";
import { ACTIVITY_TEXT, ROBOT_OUTFITS, type Activity, type RobotRole } from "./roles";

// A small humanoid robot, drawn in SVG — no image file is loaded. The body is the same for
// every agent; the outfit and one accessory depend on the role. Around it: a ring in the colour
// of the agent's activity, a status dot and (when there is one) the number of its current task.
// Every animation is a CSS animation, so "prefers-reduced-motion" switches them all off.

interface Outfit {
  /** Colour of the torso. */
  body: string;
  /** Colour of the antenna and the outline of the head. */
  accent: string;
  /** Drawn over the body (viewBox 0 0 64 64). */
  extras: ReactNode;
}

const INK = "var(--color-night-900)";
const SHIRT = "var(--color-mist-50)";

function Lapels({ tie }: { tie: string }) {
  return (
    <>
      <path d="M26.5 31h11L32 40z" fill={SHIRT} />
      <path d="M32 33.2l-1.7 2.6L32 42l1.7-6.2z" fill={tie} />
    </>
  );
}

const OUTFITS: Record<RobotRole, Outfit> = {
  // formal jacket, tie and an ID badge on a lanyard
  manager: {
    body: "var(--color-mist-400)",
    accent: "var(--color-lantern-400)",
    extras: (
      <>
        <Lapels tie="var(--color-lantern-500)" />
        <path d="M27 31l9.5 9M37 31l2.5 9" stroke="var(--color-river-300)" strokeWidth="0.9" fill="none" />
        <rect x="36" y="40" width="6.5" height="7.5" rx="1" fill={SHIRT} stroke={INK} strokeWidth="0.6" />
        <circle cx="39.2" cy="42.6" r="1.2" fill="var(--color-night-600)" />
        <path d="M37.3 45.6h3.9" stroke="var(--color-night-600)" strokeWidth="0.8" />
      </>
    ),
  },
  // helper uniform: vest with pockets, and a cap
  pion: {
    body: "var(--color-paddy-500)",
    accent: "var(--color-paddy-300)",
    extras: (
      <>
        <path d="M19.5 14.5h25l-2.2-5.6a3 3 0 0 0-2.8-1.9H24.5a3 3 0 0 0-2.8 1.9z" fill="var(--color-paddy-400)" />
        <rect x="17" y="13.4" width="30" height="2.4" rx="1.2" fill="var(--color-paddy-300)" />
        <path d="M32 31v20" stroke={INK} strokeWidth="1" opacity="0.5" />
        <rect x="22" y="36" width="6.5" height="5.5" rx="1" fill="var(--color-paddy-300)" opacity="0.9" />
        <rect x="35.5" y="36" width="6.5" height="5.5" rx="1" fill="var(--color-paddy-300)" opacity="0.9" />
      </>
    ),
  },
  // white coat, a cross and a stethoscope — an assistant, never a doctor
  doctor: {
    body: "var(--color-mist-50)",
    accent: "var(--color-river-300)",
    extras: (
      <>
        <path d="M32 31v20" stroke="var(--color-mist-400)" strokeWidth="1" />
        <path d="M26 31l6 6 6-6" stroke="var(--color-mist-400)" strokeWidth="1" fill="none" />
        <path d="M24.5 39.5v5M22 42h5" stroke="var(--color-clay-400)" strokeWidth="1.9" strokeLinecap="round" />
        <path d="M27.5 30.5c0 6 9 6 9 0M36.5 36.5v5" stroke="var(--color-river-400)" strokeWidth="1.2" fill="none" strokeLinecap="round" />
        <circle cx="36.5" cy="43" r="1.7" fill="var(--color-river-400)" />
      </>
    ),
  },
  // maintenance overall with a tool belt
  technician: {
    body: "var(--color-clay-400)",
    accent: "var(--color-clay-300)",
    extras: (
      <>
        <path d="M24 31v6h16v-6" stroke={INK} strokeWidth="1" fill="none" opacity="0.55" />
        <rect x="18.5" y="43.5" width="27" height="4" rx="1" fill={INK} opacity="0.85" />
        <rect x="30.2" y="43.9" width="3.6" height="3.2" rx="0.6" fill="var(--color-lantern-400)" />
        <rect x="21.5" y="46.5" width="5.5" height="5" rx="1" fill="var(--color-night-600)" />
        <path d="M39.5 46.5v6.2M38 52.7h3" stroke="var(--color-mist-100)" strokeWidth="1.6" strokeLinecap="round" />
      </>
    ),
  },
  // glasses and an open book
  researcher: {
    body: "var(--color-river-400)",
    accent: "var(--color-river-300)",
    extras: (
      <>
        <circle cx="27" cy="19" r="3.6" fill="none" stroke="var(--color-mist-100)" strokeWidth="0.9" />
        <circle cx="37" cy="19" r="3.6" fill="none" stroke="var(--color-mist-100)" strokeWidth="0.9" />
        <path d="M30.6 19h2.8" stroke="var(--color-mist-100)" strokeWidth="0.9" />
        <path d="M22.5 39.5l9.5 2 9.5-2v9.5l-9.5 2-9.5-2z" fill="var(--color-lantern-200)" stroke={INK} strokeWidth="0.7" />
        <path d="M32 41.5V51M25 43l4.5 1M25 45.6l4.5 1M34.5 44l4.5-1M34.5 46.6l4.5-1" stroke={INK} strokeWidth="0.7" opacity="0.7" />
      </>
    ),
  },
  // business suit and a briefcase
  sales: {
    body: "var(--color-lantern-500)",
    accent: "var(--color-lantern-300)",
    extras: (
      <>
        <Lapels tie="var(--color-river-400)" />
        <rect x="44.5" y="50" width="11" height="8" rx="1.5" fill="var(--color-night-600)" stroke="var(--color-lantern-300)" strokeWidth="0.9" />
        <path d="M48 50v-1.6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V50M44.5 53.5h11" stroke="var(--color-lantern-300)" strokeWidth="0.9" fill="none" />
      </>
    ),
  },
  default: {
    body: "var(--color-mist-400)",
    accent: "var(--color-mist-300)",
    extras: (
      <>
        <rect x="25" y="36" width="14" height="9" rx="1.5" fill={INK} opacity="0.35" />
        <circle cx="29" cy="40.5" r="1.4" fill="var(--color-paddy-300)" />
        <path d="M32.5 39h4M32.5 42h4" stroke="var(--color-mist-100)" strokeWidth="0.9" />
      </>
    ),
  },
};

const RING: Record<Activity, string> = {
  working: "border-river-400/80",
  idle: "border-paddy-500/50",
  waiting: "border-lantern-400/80",
  offline: "border-night-600",
};
const DOT: Record<Activity, string> = {
  working: "bg-river-400 animate-beacon",
  idle: "bg-paddy-400",
  waiting: "bg-lantern-400 animate-pulse",
  offline: "bg-night-500",
};

export interface RobotAvatarProps {
  role: RobotRole;
  /** working / idle / waiting / offline. Without it the robot has no ring colour and no dot. */
  status?: Activity;
  /** Edge length in pixels. */
  size?: number;
  /** The agent's name and role title: with them the avatar is announced, without them it is decoration. */
  name?: string;
  title?: string;
  /** The task the agent works on or waits with; shown as a small "#n" badge. */
  taskId?: number | null;
  className?: string;
}

/** "Mina, Study Assistant, working on task #5" */
export function robotLabel({ name, title, status, taskId, role }: Pick<RobotAvatarProps, "name" | "title" | "status" | "taskId" | "role">): string {
  const parts = [name, title].filter(Boolean) as string[];
  if (role === "doctor") parts.push("assistant only");
  if (status) {
    const task = taskId ? (status === "working" ? ` on task #${taskId}` : ` (task #${taskId})`) : "";
    parts.push(`${ACTIVITY_TEXT[status]}${task}`);
  }
  return parts.join(", ");
}

/** The robot itself, as SVG shapes for a 64 × 64 box — for use inside another <svg> (the map). */
export function RobotFigure({ role }: { role: RobotRole }) {
  const outfit = OUTFITS[role];
  return (
    <>
      {/* antenna */}
      <path d="M32 10V6" stroke={outfit.accent} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="32" cy="5" r="2" fill={outfit.accent} />
      {/* head */}
      <rect x="17" y="16" width="3.4" height="6.5" rx="1.2" fill="var(--color-night-600)" />
      <rect x="43.6" y="16" width="3.4" height="6.5" rx="1.2" fill="var(--color-night-600)" />
      <rect x="20" y="10" width="24" height="18" rx="7" fill="var(--color-night-700)" stroke={outfit.accent} strokeWidth="1.6" />
      <circle cx="27" cy="19" r="2.3" fill="var(--color-river-300)" />
      <circle cx="37" cy="19" r="2.3" fill="var(--color-river-300)" />
      <path d="M29 24h6" stroke="var(--color-mist-400)" strokeWidth="1.2" strokeLinecap="round" />
      {/* neck, arms, legs */}
      <rect x="29" y="28" width="6" height="3.5" fill="var(--color-night-600)" />
      <rect x="13" y="33" width="5.2" height="15" rx="2.6" fill={outfit.body} opacity="0.85" />
      <rect x="45.8" y="33" width="5.2" height="15" rx="2.6" fill={outfit.body} opacity="0.85" />
      <circle cx="15.6" cy="50" r="2.6" fill="var(--color-night-600)" stroke={outfit.accent} strokeWidth="0.8" />
      <circle cx="48.4" cy="50" r="2.6" fill="var(--color-night-600)" stroke={outfit.accent} strokeWidth="0.8" />
      <rect x="23" y="50" width="6.5" height="9" rx="2" fill="var(--color-night-600)" />
      <rect x="34.5" y="50" width="6.5" height="9" rx="2" fill="var(--color-night-600)" />
      <rect x="21" y="57.5" width="10.5" height="4" rx="2" fill="var(--color-night-500)" />
      <rect x="32.5" y="57.5" width="10.5" height="4" rx="2" fill="var(--color-night-500)" />
      {/* body + outfit */}
      <rect x="19" y="31" width="26" height="20.5" rx="6" fill={outfit.body} />
      {outfit.extras}
    </>
  );
}

export function RobotAvatar({ role, status, size = 48, name, title, taskId, className }: RobotAvatarProps) {
  const label = robotLabel({ name, title, status, taskId, role });
  const announced = Boolean(name || title);
  const dot = Math.max(8, Math.round(size * 0.2));
  return (
    <span
      role={announced ? "img" : undefined}
      aria-label={announced ? label : undefined}
      aria-hidden={announced ? undefined : true}
      title={announced ? `${label} — ${ROBOT_OUTFITS[role]}` : undefined}
      data-robot={role}
      data-status={status}
      className={cx("relative inline-block shrink-0 rounded-2xl border-2 bg-night-800", status ? RING[status] : "border-night-600", className)}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 64 64" width="100%" height="100%" aria-hidden="true" className={cx("block", status === "offline" && "opacity-45 grayscale")}>
        <RobotFigure role={role} />
      </svg>
      {role === "doctor" && size >= 56 && (
        <span className="absolute inset-x-0 bottom-0 rounded-b-[0.85rem] bg-night-950/85 text-center font-mono text-[7px] uppercase leading-[11px] tracking-wider text-mist-100">
          assistant only
        </span>
      )}
      {status && (
        <span
          aria-hidden="true"
          data-testid="robot-status-dot"
          className={cx("absolute -right-1 -top-1 rounded-full border-2 border-night-900", DOT[status])}
          style={{ width: dot, height: dot }}
        />
      )}
      {taskId != null && status && status !== "offline" && size >= 40 && (
        <span
          aria-hidden="true"
          data-testid="robot-task-badge"
          className={cx(
            "absolute -bottom-1.5 -right-1.5 rounded-md border border-night-900 px-1 font-mono text-[9px] font-semibold leading-[14px]",
            status === "waiting" ? "bg-lantern-400 text-night-950" : "bg-river-400 text-night-950",
          )}
        >
          #{taskId}
        </span>
      )}
    </span>
  );
}
