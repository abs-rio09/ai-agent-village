import type { KeyboardEvent, ReactNode } from "react";
import { useNavigate } from "react-router";

import type { MapAgent, MapBuilding, MapTarget, MapView } from "../../api";
import { ACTIVITY_TEXT, RobotFigure, robotRoleFor } from "../robots";
import { fitText, gridLayout, ringLayout, type Point } from "./layout";

// The village as a small town, drawn in SVG: buildings with a front, a side and a roof (a simple
// isometric look), roads, a plaza, gardens and signs. ONE level is drawn at a time. Positions come
// from components/map/layout.ts (computed from counts); nothing here knows a name.
// Buildings and robots are real controls: focusable, labelled, and usable with Enter or Space.

const STATUS_FILL: Record<MapAgent["activity"], string> = {
  working: "var(--color-river-400)",
  idle: "var(--color-paddy-400)",
  waiting: "var(--color-lantern-400)",
  offline: "var(--color-night-500)",
};
// Upazila buildings take their colour from their POSITION in the village's order.
const PALETTE = ["var(--color-river-400)", "var(--color-paddy-400)", "var(--color-lantern-300)", "var(--color-clay-300)", "var(--color-mist-300)", "var(--color-river-300)"];
const DEPTH = 14; // how far the side of a building goes back

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function buildingLabel(building: MapBuilding): string {
  const parts = [`${building.child_count} ${building.child_count === 1 ? building.child_label.replace(/s$/, "") : building.child_label}`];
  if (building.child_label !== "Agents") parts.push(plural(building.agent_count, "agent"));
  parts.push(plural(building.active_tasks, "active task"));
  return `${building.name}: ${parts.join(", ")}`;
}

export function agentLabel(agent: MapAgent): string {
  const task = agent.current_task_id ? (agent.activity === "working" ? ` on task #${agent.current_task_id}` : ` (task #${agent.current_task_id})`) : "";
  return `${agent.name}, ${agent.role}, ${ACTIVITY_TEXT[agent.activity]}${task}`;
}

interface ControlProps {
  label: string;
  onActivate: () => void;
  children: ReactNode;
  testId?: string;
  /** The focus outline, in the control's own coordinates. */
  box: { x: number; y: number; width: number; height: number };
}

/** A clickable, focusable group inside the SVG. */
function Control({ label, onActivate, children, testId, box }: ControlProps) {
  function onKeyDown(event: KeyboardEvent<SVGGElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate();
    }
  }
  return (
    <g role="link" tabIndex={0} aria-label={label} data-testid={testId} onClick={onActivate} onKeyDown={onKeyDown} className="group cursor-pointer outline-none">
      <title>{label}</title>
      {children}
      <rect {...box} rx="8" fill="none" stroke="var(--color-lantern-300)" strokeWidth="2" strokeDasharray="5 4" className="opacity-0 group-hover:opacity-60 group-focus-visible:opacity-100" />
    </g>
  );
}

/** One robot standing on the map; a link to the agent's profile. */
function MapRobot({ agent, x, y, size }: { agent: MapAgent; x: number; y: number; size: number }) {
  const navigate = useNavigate();
  return (
    <Control label={`${agentLabel(agent)} — open profile`} testId={`map-agent-${agent.id}`} onActivate={() => navigate(`/agents/profile?id=${agent.id}`)} box={{ x: x - 3, y: y - 3, width: size + 6, height: size + 6 }}>
      <ellipse cx={x + size / 2} cy={y + size - 1} rx={size * 0.36} ry={size * 0.09} fill="black" opacity="0.4" />
      <svg x={x} y={y} width={size} height={size} viewBox="0 0 64 64" opacity={agent.activity === "offline" ? 0.45 : 1}>
        <RobotFigure role={robotRoleFor(agent.template_key)} />
      </svg>
      <circle
        cx={x + size - 2}
        cy={y + 3}
        r={Math.max(3, size * 0.14)}
        fill={STATUS_FILL[agent.activity]}
        stroke="var(--color-night-900)"
        strokeWidth="1.5"
        className={agent.activity === "working" || agent.activity === "waiting" ? "animate-pulse" : undefined}
      />
    </Control>
  );
}

function Sign({ x, y, title, sub, width }: { x: number; y: number; title: string; sub: string; width: number }) {
  return (
    <g aria-hidden="true">
      <path d={`M${x} ${y - 6}v6`} stroke="var(--color-night-500)" strokeWidth="2" />
      <rect x={x - width / 2} y={y} width={width} height={sub ? 32 : 20} rx="5" fill="var(--color-night-900)" stroke="var(--color-night-600)" />
      <text x={x} y={y + 14} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="var(--color-mist-50)">
        {title}
      </text>
      {sub && (
        <text x={x} y={y + 26} textAnchor="middle" fontSize="9.5" fill="var(--color-mist-400)">
          {sub}
        </text>
      )}
    </g>
  );
}

const SIZES: Record<MapBuilding["type"], { w: number; h: number }> = {
  central: { w: 136, h: 86 },
  upazila: { w: 108, h: 70 },
  union: { w: 118, h: 74 },
  ward: { w: 92, h: 58 },
};

interface BuildingProps {
  building: MapBuilding;
  at: Point;
  scale: number;
  accent: string;
  onOpen: (target: MapTarget) => void;
}

function Building({ building, at, scale, accent, onOpen }: BuildingProps) {
  const w = SIZES[building.type].w * scale;
  const h = SIZES[building.type].h * scale;
  const d = DEPTH * scale;
  const left = at.x - w / 2;
  const top = at.y - h;
  const lit = building.active_tasks > 0;
  const gable = building.type === "union" || building.type === "ward";
  const roofTop = gable ? top - 24 * scale : top;
  const columns = building.type === "ward" ? 2 : 3;
  const rows = building.type === "central" ? 2 : 1;
  const windows: ReactNode[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      windows.push(
        <rect
          key={`${row}-${column}`}
          x={left + ((column + 0.5) * w) / columns - 6 * scale}
          y={top + 12 * scale + row * 22 * scale}
          width={12 * scale}
          height={13 * scale}
          rx="1.5"
          fill={lit ? "var(--color-lantern-300)" : "var(--color-night-500)"}
          opacity={lit ? 0.9 : 0.7}
        />,
      );
    }
  }
  const structure = (
    <>
      <ellipse cx={at.x + d / 2} cy={at.y + 3} rx={w * 0.62} ry={9 * scale} fill="black" opacity="0.35" />
      {/* side, front */}
      <path d={`M${left + w} ${top}l${d} ${-d * 0.6}v${h}l${-d} ${d * 0.6}z`} fill="var(--color-night-800)" stroke={accent} strokeOpacity="0.5" />
      <rect x={left} y={top} width={w} height={h} fill="var(--color-night-700)" stroke={accent} strokeWidth="1.4" />
      {/* roof */}
      {gable ? (
        <>
          <path d={`M${at.x} ${roofTop}l${d} ${-d * 0.6}L${left + w + 6 + d} ${top - d * 0.6}L${left + w + 6} ${top}z`} fill={accent} opacity="0.45" />
          <path d={`M${left - 6} ${top}L${at.x} ${roofTop}L${left + w + 6} ${top}z`} fill={accent} opacity="0.85" />
        </>
      ) : (
        <path d={`M${left} ${top}l${d} ${-d * 0.6}h${w}l${-d} ${d * 0.6}z`} fill={accent} opacity="0.6" />
      )}
      {building.type === "central" && (
        <>
          <rect x={at.x - 15 * scale} y={top - 30 * scale} width={30 * scale} height={30 * scale} fill="var(--color-night-700)" stroke={accent} strokeWidth="1.4" />
          <path d={`M${at.x - 19 * scale} ${top - 30 * scale}L${at.x} ${top - 46 * scale}L${at.x + 19 * scale} ${top - 30 * scale}z`} fill={accent} />
          <circle cx={at.x} cy={top - 15 * scale} r={5 * scale} fill="var(--color-lantern-200)" opacity="0.9" />
        </>
      )}
      {building.type === "upazila" && (
        <>
          <path d={`M${left + 10} ${top - d * 0.3}v${-20 * scale}`} stroke="var(--color-mist-400)" strokeWidth="1.5" />
          <path d={`M${left + 10} ${top - d * 0.3 - 20 * scale}h${13 * scale}l${-4 * scale} ${4 * scale}l${4 * scale} ${4 * scale}h${-13 * scale}z`} fill={accent} />
        </>
      )}
      {windows}
      <rect x={at.x - 7 * scale} y={at.y - 22 * scale} width={14 * scale} height={22 * scale} rx="2" fill="var(--color-night-900)" stroke={accent} strokeOpacity="0.7" />
      {/* open tasks */}
      {lit && (
        <g data-testid={`map-tasks-${building.type}-${building.id}`}>
          <circle cx={left + w + d} cy={roofTop - 2} r="11" fill="var(--color-river-400)" stroke="var(--color-night-900)" strokeWidth="2" />
          <text x={left + w + d} y={roofTop + 2} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-night-950)">
            {building.active_tasks}
          </text>
        </g>
      )}
    </>
  );
  const sub = `${building.child_count} ${building.child_count === 1 ? building.child_label.replace(/s$/, "") : building.child_label}`;
  const signWidth = Math.max(72, Math.min(w + 46, 168 * Math.max(scale, 0.86)));
  const sign = <Sign x={at.x} y={at.y + 12 + 26 * scale} title={fitText(building.name, Math.floor(signWidth / 6.3))} sub={sub} width={signWidth} />;
  const label = buildingLabel(building);
  const box = { x: left - 8, y: roofTop - (building.type === "central" ? 50 * scale : 6), width: w + d + 16, height: at.y - roofTop + (building.type === "central" ? 50 * scale : 6) + 8 };
  const robot = 26 * Math.max(scale, 0.85);
  const shown = building.agents.slice(0, 3);
  const hidden = building.agent_count - shown.length;
  const target = building.target;
  return (
    <g data-testid={`map-building-${building.type}-${building.id}`}>
      {target ? (
        <Control label={`${label} — open`} onActivate={() => onOpen(target)} box={box} testId={`map-open-${building.type}-${building.id}`}>
          {structure}
          {sign}
        </Control>
      ) : (
        <g role="img" aria-label={label}>
          <title>{label}</title>
          {structure}
          {sign}
        </g>
      )}
      {/* the first agents stand in front of their building; each is its own link */}
      {shown.map((agent, index) => (
        <MapRobot key={agent.id} agent={agent} size={robot} x={at.x - (shown.length * robot) / 2 + index * robot} y={at.y + 4} />
      ))}
      {hidden > 0 && (
        <text x={at.x + (shown.length * robot) / 2 + 4} y={at.y + 4 + robot * 0.7} fontSize="10" fill="var(--color-mist-300)" aria-hidden="true">
          +{hidden}
        </text>
      )}
    </g>
  );
}

function Garden({ at, scale }: { at: Point; scale: number }) {
  return (
    <g aria-hidden="true" opacity="0.8">
      <ellipse cx={at.x} cy={at.y + 6} rx={26 * scale} ry={9 * scale} fill="var(--color-paddy-500)" opacity="0.14" />
      {[-14, 0, 13].map((dx, index) => (
        <g key={dx}>
          <path d={`M${at.x + dx * scale} ${at.y + 4}v${-8 * scale}`} stroke="var(--color-night-500)" strokeWidth="2" />
          <circle cx={at.x + dx * scale} cy={at.y - (8 + (index % 2) * 5) * scale} r={(7 + (index % 2) * 2) * scale} fill="var(--color-paddy-500)" opacity={0.5 + index * 0.1} />
        </g>
      ))}
    </g>
  );
}

function Road({ from, to }: { from: Point; to: Point }) {
  return (
    <g aria-hidden="true">
      <path d={`M${from.x} ${from.y}L${to.x} ${to.y}`} stroke="var(--color-night-700)" strokeWidth="15" strokeLinecap="round" />
      <path d={`M${from.x} ${from.y}L${to.x} ${to.y}`} stroke="var(--color-night-500)" strokeWidth="1.2" strokeDasharray="6 8" />
    </g>
  );
}

function EmptyNote({ x, y, lines }: { x: number; y: number; lines: string[] }) {
  return (
    <g data-testid="map-empty">
      {lines.map((line, index) => (
        <text key={line} x={x} y={y + index * 17} textAnchor="middle" fontSize={index === 0 ? 13 : 11.5} fontWeight={index === 0 ? 600 : 400} fill={index === 0 ? "var(--color-mist-100)" : "var(--color-mist-400)"}>
          {line}
        </text>
      ))}
    </g>
  );
}

const EMPTY_TEXT: Record<MapView["level"], string[]> = {
  village: ["No Upazila yet", "Create one under Upazila Management."],
  upazila: ["This Upazila has no Unions yet", "Add them under Union Management."],
  union: ["This Union has no Wards yet", "Add them under Ward & Office Management."],
  ward: ["No agent works in this Office yet", "Create one under Agent Management."],
};

interface SceneProps {
  view: MapView;
  /** A phone-shaped map (narrow and tall) instead of the wide one. */
  portrait: boolean;
  onOpen: (target: MapTarget) => void;
}

export default function MapScene({ view, portrait, onOpen }: SceneProps) {
  const scale = portrait ? 0.74 : 1;
  let width: number;
  let height: number;
  let content: ReactNode;

  if (view.level === "village") {
    const central = view.buildings.find((building) => building.type === "central");
    const upazilas = view.buildings.filter((building) => building.type !== "central");
    const layout = ringLayout(upazilas.length, portrait);
    ({ width, height } = layout);
    const plaza = { rx: (portrait ? 96 : 150) * 1, ry: portrait ? 58 : 70 };
    const placed = upazilas.map((building, index) => ({ building, at: layout.slots[index]!, accent: PALETTE[index % PALETTE.length]! }));
    content = (
      <>
        {placed.map(({ building, at }) => (
          <Road key={building.id} from={layout.centre} to={at} />
        ))}
        {layout.gardens.map((at, index) => (
          <Garden key={index} at={at} scale={scale} />
        ))}
        <g aria-hidden="true">
          <ellipse cx={layout.centre.x} cy={layout.centre.y + 8} rx={plaza.rx} ry={plaza.ry} fill="var(--color-night-800)" stroke="var(--color-night-600)" strokeWidth="1.5" />
          <ellipse cx={layout.centre.x} cy={layout.centre.y + 8} rx={plaza.rx - 12} ry={plaza.ry - 8} fill="none" stroke="var(--color-night-500)" strokeDasharray="3 7" />
        </g>
        {upazilas.length === 0 && <EmptyNote x={layout.centre.x} y={layout.centre.y + plaza.ry + 96} lines={EMPTY_TEXT.village} />}
        {/* far buildings first, so the near ones are drawn over them */}
        {[...placed]
          .sort((a, b) => a.at.y - b.at.y)
          .filter(({ at }) => at.y <= layout.centre.y)
          .map(({ building, at, accent }) => (
            <Building key={building.id} building={building} at={at} scale={scale} accent={accent} onOpen={onOpen} />
          ))}
        {central && <Building building={central} at={{ x: layout.centre.x, y: layout.centre.y + 18 }} scale={scale} accent="var(--color-lantern-400)" onOpen={onOpen} />}
        {[...placed]
          .sort((a, b) => a.at.y - b.at.y)
          .filter(({ at }) => at.y > layout.centre.y)
          .map(({ building, at, accent }) => (
            <Building key={building.id} building={building} at={at} scale={scale} accent={accent} onOpen={onOpen} />
          ))}
      </>
    );
  } else if (view.level === "ward") {
    const layout = gridLayout(view.agents.length, portrait, 164, 84);
    ({ width, height } = layout);
    height = Math.max(height, 300);
    const size = portrait ? 54 : 60;
    content = (
      <>
        {/* the Office: floor, walls and its name plate */}
        <g aria-hidden="true">
          <rect x="14" y="40" width={width - 28} height={height - 58} rx="14" fill="var(--color-night-800)" stroke="var(--color-paddy-500)" strokeOpacity="0.5" strokeWidth="1.5" />
          <path d={`M14 78h${width - 28}`} stroke="var(--color-night-600)" />
          <rect x={width / 2 - 28} y={height - 24} width="56" height="8" rx="2" fill="var(--color-night-900)" stroke="var(--color-paddy-500)" strokeOpacity="0.5" />
        </g>
        <text x={width / 2} y="65" textAnchor="middle" fontSize="13" fontWeight="600" fill="var(--color-mist-50)">
          {fitText(view.office_name ?? view.name, portrait ? 40 : 80)}
        </text>
        {view.agents.length === 0 && <EmptyNote x={width / 2} y={height / 2 + 10} lines={EMPTY_TEXT.ward} />}
        {view.agents.map((agent, index) => {
          const at = layout.slots[index]!;
          return (
            <g key={agent.id} data-testid={`map-workspace-${agent.id}`}>
              <g aria-hidden="true">
                <rect x={at.x - 44} y={at.y - 30} width="88" height="12" rx="3" fill="var(--color-night-600)" />
                <path d={`M${at.x - 38} ${at.y - 18}v16M${at.x + 38} ${at.y - 18}v16`} stroke="var(--color-night-600)" strokeWidth="4" />
                <rect x={at.x + 12} y={at.y - 46} width="24" height="16" rx="2" fill="var(--color-night-900)" stroke={STATUS_FILL[agent.activity]} />
                <text x={at.x} y={at.y + 12} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="var(--color-mist-50)">
                  {fitText(agent.name, 22)}
                </text>
                <text x={at.x} y={at.y + 25} textAnchor="middle" fontSize="9.5" fill="var(--color-mist-400)">
                  {fitText(agent.role, 30)}
                </text>
                <text x={at.x} y={at.y + 38} textAnchor="middle" fontSize="9.5" fontWeight="600" fill={STATUS_FILL[agent.activity]}>
                  {agent.activity}
                  {agent.current_task_id ? ` · task #${agent.current_task_id}` : ""}
                </text>
              </g>
              <MapRobot agent={agent} size={size} x={at.x - size / 2 - 14} y={at.y - 30 - size + 8} />
            </g>
          );
        })}
      </>
    );
  } else {
    const layout = gridLayout(view.buildings.length, portrait, portrait ? 150 : 170, 70);
    ({ width, height } = layout);
    height = Math.max(height, 300);
    const rowY = Array.from(new Set(layout.slots.map((slot) => slot.y)));
    const accent = view.level === "upazila" ? "var(--color-river-400)" : "var(--color-paddy-400)";
    content = (
      <>
        {/* a street in front of every row of buildings, joined at the left */}
        {rowY.map((y) => (
          <Road key={y} from={{ x: 30, y: y + 52 }} to={{ x: width - 30, y: y + 52 }} />
        ))}
        {rowY.length > 1 && <Road from={{ x: 30, y: rowY[0]! + 52 }} to={{ x: 30, y: rowY[rowY.length - 1]! + 52 }} />}
        {rowY.map((y, index) => (
          <Garden key={y} at={{ x: index % 2 === 0 ? width - 34 : 44, y: y - 20 }} scale={scale} />
        ))}
        {view.buildings.length === 0 && <EmptyNote x={width / 2} y={height / 2} lines={EMPTY_TEXT[view.level]} />}
        {view.buildings.map((building, index) => (
          <Building key={building.id} building={building} at={{ x: layout.slots[index]!.x, y: layout.slots[index]!.y - 30 }} scale={scale} accent={accent} onOpen={onOpen} />
        ))}
      </>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="group"
      aria-label={`Map of ${view.name}`}
      data-testid="map-scene"
      data-level={view.level}
      className="block h-auto w-full select-none"
      style={{ fontFamily: "inherit" }}
    >
      <defs>
        <radialGradient id="map-ground" cx="50%" cy="45%" r="75%">
          <stop offset="0%" stopColor="var(--color-night-800)" />
          <stop offset="100%" stopColor="var(--color-night-950)" />
        </radialGradient>
      </defs>
      <rect width={width} height={height} rx="16" fill="url(#map-ground)" />
      {content}
    </svg>
  );
}
