import { ChevronDown, ChevronRight, Save } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, errorMessage, type Template } from "../api";
import { NAME_MAX, OrgIcon, RESPONSIBILITY_MAX, plural, validateName } from "../components/org";
import { Button, ErrorBanner } from "../components/ui";

// Templates are data, not code: the owner can rename a template, its Unions and its default
// Wards here. A change is used by the NEXT generation — what already exists stays as it is.

interface Draft {
  name: string;
  unions: Record<number, string>;
  wards: Record<number, { name: string; responsibility: string }>;
}

function draftOf(template: Template): Draft {
  return {
    name: template.name,
    unions: Object.fromEntries(template.unions.map((union) => [union.id, union.name])),
    wards: Object.fromEntries(template.wards.map((ward) => [ward.id, { name: ward.name, responsibility: ward.responsibility }])),
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
  const changedWards = template.wards.filter((ward) => {
    const edited = draft.wards[ward.id];
    return edited !== undefined && (edited.name.trim() !== ward.name || edited.responsibility.trim() !== ward.responsibility);
  });
  const nameChanged = draft.name.trim() !== template.name;
  const dirty = nameChanged || changedUnions.length > 0 || changedWards.length > 0;

  function edit(change: (current: Draft) => Draft) {
    setDraft(change);
    setSaved(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const names = [draft.name, ...Object.values(draft.unions), ...Object.values(draft.wards).map((ward) => ward.name)];
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
        const edited = draft.wards[ward.id]!;
        await api.updateWardTemplate(ward.id, { name: edited.name.trim(), responsibility: edited.responsibility.trim() });
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
              <div aria-hidden="true" className="hidden gap-2 text-xs text-mist-500 sm:grid sm:grid-cols-[4.5rem_1fr_1.4fr]">
                <span />
                <span>Name</span>
                <span>Responsibility</span>
              </div>
              {template.wards.map((ward) => {
                const edited = draft.wards[ward.id] ?? { name: "", responsibility: "" };
                const change = (patch: Partial<typeof edited>) =>
                  edit((current) => ({ ...current, wards: { ...current.wards, [ward.id]: { ...edited, ...patch } } }));
                return (
                  <div key={ward.id} className="grid items-center gap-2 sm:grid-cols-[4.5rem_1fr_1.4fr]">
                    <span className="font-mono text-xs text-mist-500">Ward {ward.number}</span>
                    <input
                      aria-label={`Ward ${ward.number} name`}
                      className="input"
                      maxLength={NAME_MAX}
                      value={edited.name}
                      onChange={(event) => change({ name: event.target.value })}
                    />
                    <input
                      aria-label={`Ward ${ward.number} responsibility`}
                      className="input"
                      placeholder="Responsibility (optional)"
                      maxLength={RESPONSIBILITY_MAX}
                      value={edited.responsibility}
                      onChange={(event) => change({ responsibility: event.target.value })}
                    />
                  </div>
                );
              })}
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
