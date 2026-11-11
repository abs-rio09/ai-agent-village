import { Hourglass } from "lucide-react";
import { Link } from "react-router";

import type { PageDef } from "../nav";

/** Placeholder for a page that is not built yet. It shows no data at all, by design. */
export default function ComingSoon({ page }: { page: PageDef }) {
  const Icon = page.icon;
  return (
    <section className="panel mx-auto mt-6 max-w-2xl px-8 py-12 text-center">
      <div className="mx-auto grid size-14 place-items-center rounded-2xl border border-night-600 bg-night-800 text-lantern-300">
        <Icon size={26} aria-hidden="true" />
      </div>
      <p className="eyebrow mt-6">Not built yet</p>
      <h1 className="mt-2 text-2xl font-semibold text-mist-50">{page.label}</h1>
      <p className="mt-4 inline-flex items-center gap-2 rounded-full border border-lantern-500/40 bg-lantern-500/10 px-4 py-1.5 font-mono text-xs uppercase tracking-[0.14em] text-lantern-200">
        <Hourglass size={13} aria-hidden="true" />
        Coming in M{page.milestone}
      </p>
      <p className="mx-auto mt-6 max-w-md text-sm leading-relaxed text-mist-300">{page.blurb}</p>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-mist-500">
        Nothing is shown here until the feature really exists — no sample numbers, no mock-ups.
      </p>
      <Link to="/" className="mt-8 inline-block text-sm font-medium text-lantern-300 underline-offset-4 hover:underline">
        Back to Village Overview
      </Link>
    </section>
  );
}
