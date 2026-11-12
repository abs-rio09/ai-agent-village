import { ArrowRight, Pencil, Plus, Trash } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError, api, errorMessage, type TreeUnion, type TreeUpazila } from "../api";
import { ConfirmDeleteDialog, Dialog } from "../components/Dialog";
import { Breadcrumbs, DESCRIPTION_MAX, EmptyState, PageHeader, Picker, plural, useOrgTree, validateName } from "../components/org";
import { Button, ErrorBanner, Field } from "../components/ui";

interface UnionFormProps {
  upazila: TreeUpazila;
  union: TreeUnion | null; // null = create
  onSaved: () => Promise<void>;
  onClose: () => void;
}

function UnionFormDialog({ upazila, union, onSaved, onClose }: UnionFormProps) {
  const [name, setName] = useState(union?.name ?? "");
  const [description, setDescription] = useState(union?.description ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateName(name);
    setNameError(problem);
    if (problem) return;
    setBusy(true);
    setError(null);
    const input = { name: name.trim(), description: description.trim() };
    try {
      if (union) await api.updateUnion(union.id, input);
      else await api.createUnion(upazila.id, input);
      await onSaved();
      onClose();
    } catch (cause) {
      const fieldError = cause instanceof ApiError ? cause.fieldErrors.name : undefined;
      if (fieldError) setNameError(fieldError);
      else setError(errorMessage(cause, "The Union could not be saved."));
      setBusy(false);
    }
  }

  return (
    <Dialog title={union ? "Edit Union" : `New Union in ${upazila.name}`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-2">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <Field id="union-name" label="Name" error={nameError ?? undefined} hint="1–80 characters. Must be unique in this Upazila.">
          <input
            id="union-name"
            data-autofocus
            className="input"
            value={name}
            aria-invalid={nameError ? true : undefined}
            aria-describedby="union-name-note"
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="union-description" label="Description" hint="Optional.">
          <textarea
            id="union-description"
            className="input min-h-20"
            maxLength={DESCRIPTION_MAX}
            value={description}
            aria-describedby="union-description-note"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy}>
            {union ? "Save changes" : "Create Union"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

type Modal = { type: "create" } | { type: "edit"; union: TreeUnion } | { type: "delete"; union: TreeUnion };

export default function Unions() {
  const { tree, error, reload } = useOrgTree();
  const [searchParams, setSearchParams] = useSearchParams();
  const [modal, setModal] = useState<Modal | null>(null);

  const requested = Number(searchParams.get("upazila"));
  const upazila = tree?.upazilas.find((item) => item.id === requested) ?? tree?.upazilas[0] ?? null;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[{ label: tree?.village.name ?? "Village", to: "/upazilas" }, ...(upazila ? [{ label: upazila.name }] : [])]}
      />
      <PageHeader
        title="Union Management"
        intro="Unions are the divisions inside an Upazila. Pick an Upazila to see, add, rename or delete its Unions."
        actions={
          upazila && (
            <Button onClick={() => setModal({ type: "create" })} icon={<Plus size={16} aria-hidden="true" />}>
              New Union
            </Button>
          )
        }
      />
      {error && <ErrorBanner>{error}</ErrorBanner>}

      {!tree ? (
        !error && <p className="text-sm text-mist-400">Loading the organization…</p>
      ) : !upazila ? (
        <EmptyState title="No Upazilas yet">
          <p>A Union lives inside an Upazila, so create an Upazila first.</p>
          <Link to="/upazilas" className="font-medium text-lantern-300 underline-offset-4 hover:underline">
            Go to Upazila Management
          </Link>
        </EmptyState>
      ) : (
        <>
          <Picker
            id="pick-upazila"
            label="Upazila"
            value={upazila.id}
            options={tree.upazilas}
            onChange={(id) => setSearchParams({ upazila: String(id) })}
          />

          {upazila.unions.length === 0 ? (
            <EmptyState title={`${upazila.name} has no Unions yet`}>
              <p>
                Add one with “New Union”
                {upazila.template_key
                  ? ", or use “Generate Standard Structure” in Upazila Management to create the template’s Unions, Wards and Offices."
                  : "."}
              </p>
              {upazila.template_key && (
                <Link to="/upazilas" className="font-medium text-lantern-300 underline-offset-4 hover:underline">
                  Go to Upazila Management
                </Link>
              )}
            </EmptyState>
          ) : (
            <ul className="panel divide-y divide-night-700" aria-label={`Unions of ${upazila.name}`}>
              {upazila.unions.map((union) => (
                <li key={union.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate text-[15px] font-semibold text-mist-50">{union.name}</h2>
                    {union.description && <p className="mt-0.5 truncate text-sm text-mist-400">{union.description}</p>}
                  </div>
                  <span className="shrink-0 font-mono text-xs text-mist-400">
                    {plural(union.counts.wards, "ward")} · {plural(union.counts.offices, "office")}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <Link
                      to={`/wards?union=${union.id}`}
                      aria-label={`Wards of ${union.name}`}
                      className="mr-1 inline-flex items-center gap-1 text-xs font-medium text-lantern-300 underline-offset-4 hover:underline"
                    >
                      Wards
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                    <button
                      type="button"
                      aria-label={`Edit ${union.name}`}
                      onClick={() => setModal({ type: "edit", union })}
                      className="rounded-lg p-1.5 text-mist-400 transition hover:bg-night-700 hover:text-mist-50"
                    >
                      <Pencil size={15} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${union.name}`}
                      onClick={() => setModal({ type: "delete", union })}
                      className="rounded-lg p-1.5 text-mist-400 transition hover:bg-clay-500/15 hover:text-clay-300"
                    >
                      <Trash size={15} aria-hidden="true" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {upazila && (modal?.type === "create" || modal?.type === "edit") && (
        <UnionFormDialog
          upazila={upazila}
          union={modal.type === "edit" ? modal.union : null}
          onSaved={reload}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === "delete" && (
        <ConfirmDeleteDialog
          kind="Union"
          name={modal.union.name}
          consequence={`${plural(modal.union.counts.wards, "Ward")} and ${plural(modal.union.counts.offices, "Office")}`}
          onConfirm={async () => {
            await api.deleteUnion(modal.union.id, modal.union.name);
            setModal(null);
            await reload();
          }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
