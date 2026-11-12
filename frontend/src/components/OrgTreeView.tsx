import { ChevronDown, ChevronRight, House, Landmark } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { OrgTree } from "../api";
import { OrgIcon, plural } from "./org";
import { Button } from "./ui";

// Collapsible tree of the whole organization. It is the accessible alternative to the
// future village map (SPEC §7): plain nested lists, real buttons with aria-expanded, and
// links to the page that manages each level.

function Toggle({ open, label, controls, onClick }: { open: boolean; label: string; controls: string; onClick: () => void }) {
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
      onClick={onClick}
      className="grid size-6 shrink-0 place-items-center rounded-md text-mist-400 transition hover:bg-night-700 hover:text-mist-50"
    >
      <Icon size={15} aria-hidden="true" />
    </button>
  );
}

const linkClass = "truncate font-medium text-mist-50 underline-offset-4 hover:text-lantern-300 hover:underline";

export default function OrgTreeView({ tree }: { tree: OrgTree }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());

  function toggle(key: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }

  function expandAll() {
    const all = new Set<string>();
    for (const upazila of tree.upazilas) {
      all.add(`upazila-${upazila.id}`);
      for (const union of upazila.unions) all.add(`union-${union.id}`);
    }
    setOpen(all);
  }

  return (
    <section className="panel p-5" aria-label="Organization tree">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="eyebrow">Organization tree</h2>
          <p className="mt-1 text-xs text-mist-400">
            {plural(tree.upazila_count, "Upazila")} · {plural(tree.counts.unions, "Union")} · {plural(tree.counts.wards, "Ward")} ·{" "}
            {plural(tree.counts.offices, "ward Office")}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={expandAll} disabled={tree.upazilas.length === 0}>
            Expand all
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setOpen(new Set())} disabled={open.size === 0}>
            Collapse all
          </Button>
        </div>
      </div>

      <ul className="mt-4 space-y-1 text-sm">
        <li className="flex items-center gap-2 py-1">
          <span className="grid size-6 place-items-center text-lantern-300">
            <Landmark size={15} aria-hidden="true" />
          </span>
          <span className="font-semibold text-mist-50">{tree.village.name}</span>
          <span className="eyebrow">Village</span>
        </li>
        <li>
          <ul className="ml-3 space-y-1 border-l border-night-700 pl-3">
            {tree.central_office && (
              <li className="flex items-center gap-2 py-1">
                <span className="grid size-6 place-items-center text-river-300">
                  <House size={14} aria-hidden="true" />
                </span>
                <span className="text-mist-100">{tree.central_office.name}</span>
                <span className="eyebrow">Central office</span>
              </li>
            )}
            {tree.upazilas.length === 0 && <li className="py-1 pl-8 text-mist-500">No Upazilas yet.</li>}
            {tree.upazilas.map((upazila) => {
              const upazilaKey = `upazila-${upazila.id}`;
              const upazilaOpen = open.has(upazilaKey);
              return (
                <li key={upazila.id}>
                  <div className="flex items-center gap-2 rounded-lg py-1 pr-2 hover:bg-night-800/60">
                    <Toggle open={upazilaOpen} label={upazila.name} controls={`tree-${upazilaKey}`} onClick={() => toggle(upazilaKey)} />
                    <span className="text-lantern-300">
                      <OrgIcon name={upazila.icon} size={15} />
                    </span>
                    <Link to={`/unions?upazila=${upazila.id}`} className={linkClass}>
                      {upazila.name}
                    </Link>
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-mist-500">
                      {plural(upazila.counts.unions, "union")} · {plural(upazila.counts.wards, "ward")}
                    </span>
                  </div>
                  {upazilaOpen && (
                    <ul id={`tree-${upazilaKey}`} className="ml-3 space-y-1 border-l border-night-700 pl-3">
                      {upazila.unions.length === 0 && <li className="py-1 pl-8 text-mist-500">No Unions yet.</li>}
                      {upazila.unions.map((union) => {
                        const unionKey = `union-${union.id}`;
                        const unionOpen = open.has(unionKey);
                        return (
                          <li key={union.id}>
                            <div className="flex items-center gap-2 rounded-lg py-1 pr-2 hover:bg-night-800/60">
                              <Toggle open={unionOpen} label={union.name} controls={`tree-${unionKey}`} onClick={() => toggle(unionKey)} />
                              <Link to={`/wards?union=${union.id}`} className={linkClass}>
                                {union.name}
                              </Link>
                              <span className="ml-auto shrink-0 font-mono text-[11px] text-mist-500">
                                {plural(union.counts.wards, "ward")}
                              </span>
                            </div>
                            {unionOpen && (
                              <ul id={`tree-${unionKey}`} className="ml-3 space-y-0.5 border-l border-night-700 pl-3">
                                {union.wards.length === 0 && <li className="py-1 pl-8 text-mist-500">No Wards yet.</li>}
                                {union.wards.map((ward) => (
                                  <li key={ward.id} className="flex flex-wrap items-baseline gap-x-2 py-0.5 pl-8">
                                    <span className="font-mono text-[11px] text-mist-500">Ward {ward.number}</span>
                                    <Link to={`/wards?union=${union.id}&ward=${ward.id}`} className={linkClass}>
                                      {ward.name}
                                    </Link>
                                    {ward.office && <span className="text-xs text-mist-400">— {ward.office.name}</span>}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </li>
      </ul>
    </section>
  );
}
