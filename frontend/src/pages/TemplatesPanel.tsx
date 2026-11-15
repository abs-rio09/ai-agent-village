import { ChevronDown, ChevronRight, Plus, Save, Trash } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, errorMessage, type Template } from "../api";
import { NAME_MAX, OrgIcon, RESPONSIBILITY_MAX, plural, validateName } from "../components/org";
import { Button, ErrorBanner } from "../components/ui";

// Templates are data, not code: the owner can rename a template, its Unions and its default
// Wards here, and add or remove default Wards (never more than template.max_wards, which the
// server sends). A change is used by the NEXT generation — what already exists stays as it is.

interface DraftWard {
  id: number | null; // null = added here, not saved yet
  name: string;
  responsibility: string;
}

interface Draft {
  name: string;
  unions: Record<number, string>;
  wards: DraftWard[];
}

function draftOf(template: Template): Draft {
  return {
    name: template.name,
    unions: Object.fromEntries(template.unions.map((union) => [union.id, union.name])),
    wards: template.wards.map((ward) => ({ id: ward.id, name: ward.name, responsibility: ward.responsibility })),
  };
}

function TemplateEditor({ template, onChanged }: { template: Template; onChanged: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => draftOf(template));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const base = `template-${template.key}`;

  const changedUnions = template.unions.filter((union) => (draft.unions[union.id] ?? "").trim() !== union.name);
  // Same rows in the same order → per-ward edits; rows added or removed → the whole set is saved.
  const wardSetChanged =
    draft.wards.length !== template.wards.length || draft.wards.some((ward, index) => ward.id !== template.wards[index]?.id);
  const changedWards = wardSetChanged
    ? []
    : template.wards.filter((ward, index) => {
        const edited = draft.wards[index]!;
        return edited.name.trim() !== ward.name || edited.responsibility.trim() !== ward.responsibility;
      });
  const nameChanged = draft.name.trim() !== template.name;
  const dirty = nameChanged || changedUnions.length > 0 || changedWards.length > 0 || wardSetChanged;
  const atLimit = draft.wards.length >= template.max_wards;

  function edit(change: (current: Draft) => Draft) {
    setDraft(change);
    setSaved(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const names = [draft.name, ...Object.values(draft.unions), ...draft.wards.map((ward) => ward.name)];
    const problem = names.map((value) => validateName(value)).find((message) => message !== null);
    if (problem) {
      setError(`Every name must be filled in. ${problem}`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (nameChanged) await api.updateTemplate(template.key, { name: draft.name.trim() });
      for (const union of changedUnions) {
        await api.updateUnionTemplate(union.id, (draft.unions[union.id] ?? "").trim());
      }
      for (const ward of changedWards) {
        const edited = draft.wards[template.wards.indexOf(ward)]!;
        await api.updateWardTemplate(ward.id, { name: edited.name.trim(), responsibility: edited.responsibility.trim() });
      }
      if (wardSetChanged) {
        const updated = await api.replaceWardTemplates(
          template.key,
          draft.wards.map((ward) => ({ name: ward.name.trim(), responsibility: ward.responsibility.trim() })),
        );
        setDraft(draftOf(updated)); // the rows now have their saved ids and numbers
      }
      setSaved(true);
    } catch (cause) {
      setError(errorMessage(cause, "The template could not be saved."));
    } finally {
      await onChanged(); // show what the server really has, also after a partial failure
      setBusy(false);
    }
  }

  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section className="panel" aria-label={`Template ${template.name}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${base}-body`}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-3 rounded-2xl px-5 py-4 text-left transition hover:bg-night-800/50"
      >
        <Chevron size={16} aria-hidden="true" className="shrink-0 text-mist-400" />
        <span className="text-lantern-300">
          <OrgIcon name={template.icon} />
        </span>
        <span className="min-w-0 flex-1 truncate font-semibold text-mist-50">{template.name}</span>
        <span className="shrink-0 font-mono text-[11px] text-mist-500">
          {plural(template.unions.length, "union")} · {plural(template.wards.length, "ward")} each
        </span>
      </button>

      {open && (
        <form id={`${base}-body`} onSubmit={handleSubmit} noValidate className="space-y-5 border-t border-night-700 px-5 py-5">
          {error && <ErrorBanner>{error}</ErrorBanner>}

          <div>
            <label htmlFor={`${base}-name`} className="eyebrow mb-1.5 block">
              Template name
            </label>
            <input
              id={`${base}-name`}
              className="input max-w-md"
              maxLength={NAME_MAX}
              value={draft.name}
              onChange={(event) => edit((current) => ({ ...current, name: event.target.value }))}
            />
          </div>

          <fieldset>
            <legend className="eyebrow mb-1.5">Unions</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {template.unions.map((union, index) => (
                <input
                  key={union.id}
                  aria-label={`Union ${index + 1} name`}
                  className="input"
                  maxLength={NAME_MAX}
                  value={draft.unions[union.id] ?? ""}
                  onChange={(event) =>
                    edit((current) => ({ ...current, unions: { ...current.unions, [union.id]: event.target.value } }))
                  }
                />
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="eyebrow mb-1.5">Default Wards of every Union</legend>
            <div className="space-y-2">
              <div aria-hidden="true" className="hidden gap-2 text-xs text-mist-500 sm:grid sm:grid-cols-[4.5rem_1fr_1.4fr_auto]">
                <span />
                <span>Name</span>
                <span>Responsibility</span>
                <span className="w-7" />
              </div>
              {draft.wards.map((ward, index) => {
                const number = index + 1;
                const change = (patch: Partial<DraftWard>) =>
                  edit((current) => ({
                    ...current,
                    wards: current.wards.map((item, at) => (at === index ? { ...item, ...patch } : item)),
                  }));
                return (
                  <div key={ward.id ?? `new-${index}`} className="grid items-center gap-2 sm:grid-cols-[4.5rem_1fr_1.4fr_auto]">
                    <span className="font-mono text-xs text-mist-500">Ward {number}</span>
                    <input
                      aria-label={`Ward ${number} name`}
                      className="input"
                      maxLength={NAME_MAX}
                      value={ward.name}
                      onChange={(event) => change({ name: event.target.value })}
                    />
                    <input
                      aria-label={`Ward ${number} responsibility`}
                      className="input"
                      placeholder="Responsibility (optional)"
                      maxLength={RESPONSIBILITY_MAX}
                      value={ward.responsibility}
                      onChange={(event) => change({ responsibility: event.target.value })}
                    />
                    <button
                      type="button"
                      aria-label={`Remove ward ${number}`}
                      disabled={draft.wards.length <= 1}
                      onClick={() => edit((current) => ({ ...current, wards: current.wards.filter((_, at) => at !== index) }))}
                      className="justify-self-start rounded-lg p-1.5 text-mist-400 transition hover:bg-clay-500/15 hover:text-clay-300 disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <Trash size={14} aria-hidden="true" />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="mt-3">
              {atLimit ? (
                <p role="note" className="text-sm text-mist-400">
                  Maximum {template.max_wards} wards per Union
                </p>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Plus size={14} aria-hidden="true" />}
                  onClick={() =>
                    edit((current) =>
                      current.wards.length >= template.max_wards
                        ? current
                        : { ...current, wards: [...current.wards, { id: null, name: "", responsibility: "" }] },
                    )
                  }
                >
                  Add ward name
                </Button>
              )}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-center justify-end gap-3">
            {saved && !dirty && (
              <p role="status" className="text-sm text-paddy-300">
                Saved. Used by the next generation.
              </p>
            )}
            <Button variant="ghost" onClick={() => edit(() => draftOf(template))} disabled={!dirty || busy}>
              Reset
            </Button>
            <Button type="submit" disabled={!dirty} busy={busy} icon={<Save size={16} aria-hidden="true" />}>
              Save template
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function TemplatesPanel({ templates, onChanged }: { templates: Template[]; onChanged: () => Promise<void> }) {
  return (
    <div className="space-y-3">
      <p className="max-w-3xl text-sm text-mist-400">
        A template is the suggested structure of an Upazila: its Unions and the Wards every Union starts with. Changes here apply
        to <strong className="font-semibold text-mist-100">future</strong> “Generate Standard Structure” runs only — Upazilas,
        Unions and Wards that already exist are not renamed.
      </p>
      {templates.map((template) => (
        <TemplateEditor key={template.key} template={template} onChanged={onChanged} />
      ))}
    </div>
  );
}
