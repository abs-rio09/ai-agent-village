import { ArrowRight, Pencil, Plus, Sparkles, Trash } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError, api, errorMessage, type GenerateResult, type Template, type TreeUpazila } from "../api";
import { ConfirmDeleteDialog, Dialog } from "../components/Dialog";
import OrgTreeView from "../components/OrgTreeView";
import {
  Breadcrumbs,
  DESCRIPTION_MAX,
  EmptyState,
  ICON_OPTIONS,
  OrgIcon,
  PageHeader,
  plural,
  useOrgTree,
  validateName,
} from "../components/org";
import { Button, ErrorBanner, Field, cx } from "../components/ui";
import TemplatesPanel from "./TemplatesPanel";

// ---------------------------------------------------------------- create / edit


interface UpazilaFormProps {
  upazila: TreeUpazila | null; // null = create
  templates: Template[];
  onSaved: () => Promise<void>;
  onClose: () => void;
}

export function UpazilaFormDialog({ upazila, templates, onSaved, onClose }: UpazilaFormProps) {
  const [name, setName] = useState(upazila?.name ?? "");
  const [description, setDescription] = useState(upazila?.description ?? "");
  const [icon, setIcon] = useState(upazila?.icon ?? "");
  const [templateKey, setTemplateKey] = useState(upazila?.template_key ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function chooseTemplate(key: string) {
    setTemplateKey(key);
    const template = templates.find((item) => item.key === key);
    if (template && !upazila && !icon) setIcon(template.icon); // a new Upazila takes the template's icon
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateName(name);
    setNameError(problem);
    if (problem) return;
    setBusy(true);
    setError(null);
    const input = { name: name.trim(), description: description.trim(), icon, template_key: templateKey || null };
    try {
      if (upazila) await api.updateUpazila(upazila.id, input);
      else await api.createUpazila(input);
      await onSaved();
      onClose();
    } catch (cause) {
      const fieldError = cause instanceof ApiError ? cause.fieldErrors.name : undefined;
      if (fieldError) setNameError(fieldError);
      else setError(errorMessage(cause, "The Upazila could not be saved."));
      setBusy(false);
    }
  }

  return (
    <Dialog title={upazila ? "Edit Upazila" : "New Upazila"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-2">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <Field id="upazila-name" label="Name" error={nameError ?? undefined} hint="1–80 characters. Must be unique in the village.">
          <input
            id="upazila-name"
            data-autofocus
            className="input"
            value={name}
            aria-invalid={nameError ? true : undefined}
            aria-describedby="upazila-name-note"
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="upazila-description" label="Description" hint="Optional.">
          <textarea
            id="upazila-description"
            className="input min-h-20"
            maxLength={DESCRIPTION_MAX}
            value={description}
            aria-describedby="upazila-description-note"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <div className="grid gap-x-4 sm:grid-cols-2">
          <Field id="upazila-template" label="Template" hint="Needed for “Generate Standard Structure”.">
            <select
              id="upazila-template"
              className="input"
              value={templateKey}
              aria-describedby="upazila-template-note"
              onChange={(event) => chooseTemplate(event.target.value)}
            >
              <option value="">No template (custom)</option>
              {templates.map((template) => (
                <option key={template.key} value={template.key}>
                  {template.name}
                </option>
              ))}
            </select>
          </Field>
          <Field id="upazila-icon" label="Icon">
            <select id="upazila-icon" className="input" value={icon} onChange={(event) => setIcon(event.target.value)}>
              {!ICON_OPTIONS.some((option) => option.key === icon) && <option value={icon}>{icon}</option>}
              {ICON_OPTIONS.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy}>
            {upazila ? "Save changes" : "Create Upazila"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------- generate standard structure


function CountTiles({ result, prefix }: { result: GenerateResult; prefix: string }) {
  const tiles = [
    { key: "unions", label: "Unions", value: result.unions_created },
    { key: "wards", label: "Wards", value: result.wards_created },
    { key: "offices", label: "Offices", value: result.offices_created },
  ];
  return (
    <dl className="grid grid-cols-3 gap-3">
      {tiles.map((tile) => (
        <div key={tile.key} className="rounded-xl border border-night-600 bg-night-900 px-4 py-3 text-center">
          <dd data-testid={`${prefix}-${tile.key}`} className="font-mono text-2xl tabular-nums text-mist-50">
            {tile.value}
          </dd>
          <dt className="eyebrow mt-1">{tile.label}</dt>
        </div>
      ))}
    </dl>
  );
}

interface GenerateProps {
  upazila: TreeUpazila;
  onGenerated: () => Promise<void>;
  onClose: () => void;
}

/** Preview counts → Confirm → result counts. Nothing is written until Confirm. */
export function GenerateDialog({ upazila, onGenerated, onClose }: GenerateProps) {
  const [preview, setPreview] = useState<GenerateResult | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .previewStandardStructure(upazila.id)
      .then((counts) => !cancelled && setPreview(counts))
      .catch((cause: unknown) => !cancelled && setError(errorMessage(cause, "Could not load the preview.")));
    return () => {
      cancelled = true;
    };
  }, [upazila.id]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.generateStandardStructure(upazila.id));
      await onGenerated();
    } catch (cause) {
      setError(errorMessage(cause, "The structure could not be generated."));
    } finally {
      setBusy(false);
    }
  }

  const nothingToDo = preview !== null && preview.unions_created === 0;
  const skippedNote = (count: number) =>
    count > 0 && (
      <p className="text-xs text-mist-400">
        {plural(count, "template Union")} already {count === 1 ? "exists" : "exist"} in this Upazila and {count === 1 ? "is" : "are"} left
        untouched.
      </p>
    );

  return (
    <Dialog title="Generate Standard Structure" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-mist-300">
          Upazila <strong className="font-semibold text-mist-50">{upazila.name}</strong>
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}

        {result ? (
          <>
            <h3 className="text-sm font-semibold text-paddy-300">Created</h3>
            <CountTiles result={result} prefix="result" />
            {skippedNote(result.skipped)}
            <div className="flex justify-end">
              <Button onClick={onClose}>Done</Button>
            </div>
          </>
        ) : preview ? (
          <>
            <h3 className="text-sm font-semibold text-mist-100">
              {nothingToDo ? "Nothing to create" : "This will create"}
            </h3>
            <CountTiles result={preview} prefix="preview" />
            {skippedNote(preview.skipped)}
            {!nothingToDo && (
              <p className="text-xs text-mist-400">
                Every new Ward gets its own Office. Names come from the template and can be changed afterwards.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>
                {nothingToDo ? "Close" : "Cancel"}
              </Button>
              {!nothingToDo && (
                <Button onClick={() => void confirm()} busy={busy} icon={<Sparkles size={16} aria-hidden="true" />}>
                  Confirm
                </Button>
              )}
            </div>
          </>
        ) : (
          !error && <p className="text-sm text-mist-400">Loading preview…</p>
        )}
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------- cards


interface CardProps {
  upazila: TreeUpazila;
  templateName: string | null;
  onEdit: () => void;
  onDelete: () => void;
  onGenerate: () => void;
}

function UpazilaCard({ upazila, templateName, onEdit, onDelete, onGenerate }: CardProps) {
  const counts = [
    { label: "Unions", value: upazila.counts.unions },
    { label: "Wards", value: upazila.counts.wards },
    { label: "Offices", value: upazila.counts.offices },
  ];
  return (
    <article className="panel flex flex-col p-5" aria-label={upazila.name}>
      <div className="flex items-start gap-3">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-night-600 bg-night-800 text-lantern-300">
          <OrgIcon name={upazila.icon} size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-mist-50">{upazila.name}</h2>
          <p className="mt-0.5 truncate text-xs text-mist-500">{templateName ? `Template: ${templateName}` : "Custom Upazila"}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            aria-label={`Edit ${upazila.name}`}
            onClick={onEdit}
            className="rounded-lg p-1.5 text-mist-400 transition hover:bg-night-700 hover:text-mist-50"
          >
            <Pencil size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={`Delete ${upazila.name}`}
            onClick={onDelete}
            className="rounded-lg p-1.5 text-mist-400 transition hover:bg-clay-500/15 hover:text-clay-300"
          >
            <Trash size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      {upazila.description && <p className="mt-3 line-clamp-2 text-sm text-mist-300">{upazila.description}</p>}

      <dl className="mt-4 grid grid-cols-3 gap-2">
        {counts.map((count) => (
          <div key={count.label} className="rounded-lg border border-night-700 bg-night-900/70 px-3 py-2">
            <dd className="font-mono text-lg tabular-nums text-mist-50">{count.value}</dd>
            <dt className="eyebrow !text-[10px]">{count.label}</dt>
          </div>
        ))}
      </dl>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 pt-1">
        {upazila.template_key ? (
          <Button variant="ghost" size="sm" onClick={onGenerate} icon={<Sparkles size={14} aria-hidden="true" />}>
            Generate Standard Structure
          </Button>
        ) : (
          <span className="text-xs text-mist-500">No template — add Unions by hand.</span>
        )}
        <Link
          to={`/unions?upazila=${upazila.id}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-lantern-300 underline-offset-4 hover:underline"
        >
          Unions
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------- page


type Tab = "upazilas" | "tree" | "templates";
const TABS: Array<{ id: Tab; label: string }> = [
  { id: "upazilas", label: "Upazilas" },
  { id: "tree", label: "Tree view" },
  { id: "templates", label: "Templates" },
];

type Modal =
  | { type: "create" }
  | { type: "edit"; upazila: TreeUpazila }
  | { type: "delete"; upazila: TreeUpazila }
  | { type: "generate"; upazila: TreeUpazila };

export default function Upazilas() {
  const { tree, error, reload } = useOrgTree();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [modal, setModal] = useState<Modal | null>(null);
  const [standardBusy, setStandardBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const requested = searchParams.get("tab");
  const tab: Tab = TABS.some((item) => item.id === requested) ? (requested as Tab) : "upazilas";

  async function loadTemplates() {
    try {
      setTemplates(await api.templates());
      setTemplatesError(null);
    } catch (cause) {
      setTemplatesError(errorMessage(cause, "Could not load the templates."));
    }
  }

  useEffect(() => {
    void loadTemplates();
  }, []);

  async function createStandard() {
    setStandardBusy(true);
    setActionError(null);
    try {
      await api.createStandardUpazilas();
      await reload();
    } catch (cause) {
      setActionError(errorMessage(cause, "The standard Upazilas could not be created."));
    } finally {
      setStandardBusy(false);
    }
  }

  const templateName = (key: string | null) => templates?.find((template) => template.key === key)?.name ?? null;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: tree?.village.name ?? "Village" }]} />
      <PageHeader
        title="Upazila Management"
        intro="Upazilas are the top-level departments of the village. Create your own, or start from a template and generate its standard Unions, Wards and Offices."
        actions={
          <Button onClick={() => setModal({ type: "create" })} icon={<Plus size={16} aria-hidden="true" />}>
            New Upazila
          </Button>
        }
      />

      <div role="tablist" aria-label="Upazila Management views" className="flex gap-1 border-b border-night-700">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls="upazila-tabpanel"
            onClick={() => setSearchParams(item.id === "upazilas" ? {} : { tab: item.id }, { replace: true })}
            className={cx(
              "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition",
              tab === item.id ? "border-lantern-400 text-mist-50" : "border-transparent text-mist-400 hover:text-mist-100",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="upazila-tabpanel" aria-labelledby={`tab-${tab}`} className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        {actionError && <ErrorBanner>{actionError}</ErrorBanner>}
        {templatesError && tab !== "tree" && <ErrorBanner>{templatesError}</ErrorBanner>}

        {tab === "templates" ? (
          templates ? (
            <TemplatesPanel templates={templates} onChanged={loadTemplates} />
          ) : (
            !templatesError && <p className="text-sm text-mist-400">Loading templates…</p>
          )
        ) : !tree ? (
          !error && <p className="text-sm text-mist-400">Loading the organization…</p>
        ) : tab === "tree" ? (
          <OrgTreeView tree={tree} />
        ) : tree.upazilas.length === 0 ? (
          <EmptyState title="No Upazilas yet">
            <p>
              Nothing is created automatically. Start with the standard Upazilas from the templates, or create your own with
              “New Upazila”.
            </p>
            {templates && templates.length > 0 && (
              <Button onClick={() => void createStandard()} busy={standardBusy} icon={<Sparkles size={16} aria-hidden="true" />}>
                Create the {templates.length} standard Upazilas
              </Button>
            )}
          </EmptyState>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tree.upazilas.map((upazila) => (
              <UpazilaCard
                key={upazila.id}
                upazila={upazila}
                templateName={templateName(upazila.template_key)}
                onEdit={() => setModal({ type: "edit", upazila })}
                onDelete={() => setModal({ type: "delete", upazila })}
                onGenerate={() => setModal({ type: "generate", upazila })}
              />
            ))}
          </div>
        )}
      </div>

      {(modal?.type === "create" || modal?.type === "edit") && (
        <UpazilaFormDialog
          upazila={modal.type === "edit" ? modal.upazila : null}
          templates={templates ?? []}
          onSaved={reload}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === "generate" && (
        <GenerateDialog upazila={modal.upazila} onGenerated={reload} onClose={() => setModal(null)} />
      )}
      {modal?.type === "delete" && (
        <ConfirmDeleteDialog
          kind="Upazila"
          name={modal.upazila.name}
          consequence={`${plural(modal.upazila.counts.unions, "Union")}, ${plural(modal.upazila.counts.wards, "Ward")} and ${plural(modal.upazila.counts.offices, "Office")}`}
          onConfirm={async () => {
            await api.deleteUpazila(modal.upazila.id, modal.upazila.name);
            setModal(null);
            await reload();
          }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
