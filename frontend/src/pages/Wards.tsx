import { House, Landmark, Pencil, Plus, Trash } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage, type Office, type TreeUnion, type TreeWard } from "../api";
import { ConfirmDeleteDialog } from "../components/Dialog";
import {
  Breadcrumbs,
  DESCRIPTION_MAX,
  EmptyState,
  NAME_MAX,
  PageHeader,
  Picker,
  RESPONSIBILITY_MAX,
  useOrgTree,
  validateName,
  type Crumb,
} from "../components/org";
import { Button, ErrorBanner, cx } from "../components/ui";

// ---------------------------------------------------------------- one ward (card + inline edit)


interface WardCardProps {
  ward: TreeWard;
  selected: boolean;
  editing: boolean;
  onEdit: () => void;
  onDone: () => void;
  onDelete: () => void;
  onSaved: () => Promise<void>;
}

function WardCard({ ward, selected, editing, onEdit, onDone, onDelete, onSaved }: WardCardProps) {
  const [name, setName] = useState(ward.name);
  const [responsibility, setResponsibility] = useState(ward.responsibility);
  const [officeName, setOfficeName] = useState(ward.office?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `ward-${ward.id}`;

  function startEditing() {
    setName(ward.name);
    setResponsibility(ward.responsibility);
    setOfficeName(ward.office?.name ?? "");
    setError(null);
    onEdit();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateName(name, "a ward name") ?? (ward.office ? validateName(officeName, "an office name") : null);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (name.trim() !== ward.name || responsibility.trim() !== ward.responsibility) {
        await api.updateWard(ward.id, { name: name.trim(), responsibility: responsibility.trim() });
      }
      // Only when the owner typed a different office name; otherwise the server keeps an
      // automatic "<ward name> Office" in step with the ward's new name.
      if (ward.office && officeName.trim() !== ward.office.name) {
        await api.updateOffice(ward.office.id, { name: officeName.trim() });
      }
      await onSaved();
      onDone();
    } catch (cause) {
      setError(errorMessage(cause, "The ward could not be saved."));
      await onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      aria-label={`Ward ${ward.number}: ${ward.name}`}
      className={cx("panel flex flex-col p-4", selected && "!border-lantern-400/70 shadow-[0_0_0_3px_rgb(246_181_69/0.12)]")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-md border border-night-600 bg-night-900 px-2 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mist-300">
          Ward {ward.number}
        </span>
        {!editing && (
          <div className="flex gap-1">
            <button
              type="button"
              aria-label={`Edit ward ${ward.number}`}
              onClick={startEditing}
              className="rounded-lg p-1.5 text-mist-400 transition hover:bg-night-700 hover:text-mist-50"
            >
              <Pencil size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              aria-label={`Delete ward ${ward.number}`}
              onClick={onDelete}
              className="rounded-lg p-1.5 text-mist-400 transition hover:bg-clay-500/15 hover:text-clay-300"
            >
              <Trash size={14} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <form onSubmit={handleSubmit} noValidate className="mt-3 space-y-2.5">
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <div>
            <label htmlFor={`${base}-name`} className="eyebrow mb-1 block !text-[10px]">
              Ward name
            </label>
            <input
              id={`${base}-name`}
              autoFocus
              className="input"
              maxLength={NAME_MAX}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor={`${base}-responsibility`} className="eyebrow mb-1 block !text-[10px]">
              Responsibility
            </label>
            <textarea
              id={`${base}-responsibility`}
              className="input min-h-16"
              maxLength={RESPONSIBILITY_MAX}
              value={responsibility}
              onChange={(event) => setResponsibility(event.target.value)}
            />
          </div>
          {ward.office && (
            <div>
              <label htmlFor={`${base}-office`} className="eyebrow mb-1 block !text-[10px]">
                Office name
              </label>
              <input
                id={`${base}-office`}
                className="input"
                maxLength={NAME_MAX}
                value={officeName}
                onChange={(event) => setOfficeName(event.target.value)}
              />
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={onDone} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" size="sm" busy={busy}>
              Save
            </Button>
          </div>
        </form>
      ) : (
        <>
          <h2 className="mt-3 text-[15px] font-semibold leading-snug text-mist-50">{ward.name}</h2>
          <p className={cx("mt-1 text-sm leading-snug", ward.responsibility ? "text-mist-300" : "text-mist-500")}>
            {ward.responsibility || "No responsibility set"}
          </p>
          <p className="mt-auto flex items-center gap-1.5 pt-3 text-xs text-mist-400">
            <House size={13} aria-hidden="true" className="shrink-0 text-river-300" />
            <span className="truncate">{ward.office ? ward.office.name : "No office"}</span>
          </p>
        </>
      )}
    </article>
  );
}

// ---------------------------------------------------------------- central administration


function CentralOfficePanel({ office, onSaved }: { office: Office; onSaved: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(office.name);
  const [description, setDescription] = useState(office.description);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateName(name, "an office name");
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.updateOffice(office.id, { name: name.trim(), description: description.trim() });
      await onSaved();
      setEditing(false);
    } catch (cause) {
      setError(errorMessage(cause, "The office could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5" aria-label="Central Administration office">
      <div className="flex items-start gap-3">
        <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-night-600 bg-night-800 text-river-300">
          <Landmark size={18} aria-hidden="true" />
        </div>
        {editing ? (
          <form onSubmit={handleSubmit} noValidate className="min-w-0 flex-1 space-y-2.5">
            {error && <ErrorBanner>{error}</ErrorBanner>}
            <div>
              <label htmlFor="central-office-name" className="eyebrow mb-1 block !text-[10px]">
                Central office name
              </label>
              <input
                id="central-office-name"
                autoFocus
                className="input max-w-md"
                maxLength={NAME_MAX}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="central-office-description" className="eyebrow mb-1 block !text-[10px]">
                Description
              </label>
              <textarea
                id="central-office-description"
                className="input min-h-16"
                maxLength={DESCRIPTION_MAX}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" size="sm" busy={busy}>
                Save
              </Button>
            </div>
          </form>
        ) : (
          <>
            <div className="min-w-0 flex-1">
              <p className="eyebrow">Central office · belongs to the village, not to a ward</p>
              <h2 className="mt-1 truncate text-base font-semibold text-mist-50">{office.name}</h2>
              <p className={cx("mt-0.5 text-sm", office.description ? "text-mist-300" : "text-mist-500")}>
                {office.description || "No description"}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              icon={<Pencil size={13} aria-hidden="true" />}
              onClick={() => {
                setName(office.name);
                setDescription(office.description);
                setError(null);
                setEditing(true);
              }}
            >
              Edit central office
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- page


export default function Wards() {
  const { tree, error, reload } = useOrgTree();
  const [searchParams, setSearchParams] = useSearchParams();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<TreeWard | null>(null);
  const [addBusy, setAddBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // ?union= wins; otherwise ?upazila=; otherwise the first Upazila and its first Union.
  const requestedUnion = Number(searchParams.get("union"));
  const requestedUpazila = Number(searchParams.get("upazila"));
  const upazilas = tree?.upazilas ?? [];
  const upazila =
    upazilas.find((item) => item.unions.some((union) => union.id === requestedUnion)) ??
    upazilas.find((item) => item.id === requestedUpazila) ??
    upazilas[0] ??
    null;
  const union: TreeUnion | null = upazila?.unions.find((item) => item.id === requestedUnion) ?? upazila?.unions[0] ?? null;
  const selectedWard = union?.wards.find((ward) => ward.id === Number(searchParams.get("ward"))) ?? null;

  function show(params: Record<string, number>) {
    setEditingId(null);
    setSearchParams(Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])));
  }

  async function addWard() {
    if (!union) return;
    setAddBusy(true);
    setActionError(null);
    try {
      const ward = await api.createWard(union.id);
      await reload();
      show({ union: union.id, ward: ward.id });
      setEditingId(ward.id); // name it straight away
    } catch (cause) {
      setActionError(errorMessage(cause, "The ward could not be added."));
    } finally {
      setAddBusy(false);
    }
  }

  const crumbs: Crumb[] = [{ label: tree?.village.name ?? "Village", to: "/upazilas" }];
  if (upazila) crumbs.push({ label: upazila.name, to: `/unions?upazila=${upazila.id}` });
  if (union) crumbs.push({ label: union.name, to: `/wards?union=${union.id}` });
  if (selectedWard) crumbs.push({ label: `Ward ${selectedWard.number}: ${selectedWard.name}` });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={crumbs} />
      <PageHeader
        title="Ward & Office Management"
        intro="Every Union is divided into numbered Wards, and every Ward has one Office. Pick a Union to rename its Wards, set their responsibilities and name their Offices."
        actions={
          union && (
            <Button onClick={() => void addWard()} busy={addBusy} icon={<Plus size={16} aria-hidden="true" />}>
              Add ward
            </Button>
          )
        }
      />
      {error && <ErrorBanner>{error}</ErrorBanner>}
      {actionError && <ErrorBanner>{actionError}</ErrorBanner>}

      {!tree ? (
        !error && <p className="text-sm text-mist-400">Loading the organization…</p>
      ) : (
        <>
          {!upazila ? (
            <EmptyState title="No Upazilas yet">
              <p>Wards live inside a Union, and Unions inside an Upazila. Create an Upazila first.</p>
              <Link to="/upazilas" className="font-medium text-lantern-300 underline-offset-4 hover:underline">
                Go to Upazila Management
              </Link>
            </EmptyState>
          ) : (
            <>
              <div className="flex flex-wrap gap-4">
                <Picker
                  id="pick-upazila"
                  label="Upazila"
                  value={upazila.id}
                  options={upazilas}
                  onChange={(id) => show({ upazila: id })}
                />
                <Picker
                  id="pick-union"
                  label="Union"
                  value={union?.id ?? null}
                  options={upazila.unions}
                  onChange={(id) => show({ union: id })}
                />
              </div>

              {!union ? (
                <EmptyState title={`${upazila.name} has no Unions yet`}>
                  <p>Create a Union first, then add Wards to it.</p>
                  <Link
                    to={`/unions?upazila=${upazila.id}`}
                    className="font-medium text-lantern-300 underline-offset-4 hover:underline"
                  >
                    Go to Union Management
                  </Link>
                </EmptyState>
              ) : union.wards.length === 0 ? (
                <EmptyState title={`${union.name} has no Wards yet`}>
                  <p>Use “Add ward” to create Ward 1 and its Office.</p>
                </EmptyState>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={`Wards of ${union.name}`} role="group">
                  {union.wards.map((ward) => (
                    <WardCard
                      key={ward.id}
                      ward={ward}
                      selected={selectedWard?.id === ward.id}
                      editing={editingId === ward.id}
                      onEdit={() => {
                        setEditingId(ward.id);
                        setSearchParams({ union: String(union.id), ward: String(ward.id) }, { replace: true });
                      }}
                      onDone={() => setEditingId(null)}
                      onDelete={() => setDeleting(ward)}
                      onSaved={reload}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {tree.central_office && (
            <CentralOfficePanel key={tree.central_office.id} office={tree.central_office} onSaved={reload} />
          )}
        </>
      )}

      {deleting && union && (
        <ConfirmDeleteDialog
          kind="Ward"
          name={deleting.name}
          consequence={deleting.office ? `its Office “${deleting.office.name}”` : ""}
          onConfirm={async () => {
            await api.deleteWard(deleting.id, deleting.name);
            setDeleting(null);
            setEditingId(null);
            setSearchParams({ union: String(union.id) }, { replace: true });
            await reload();
          }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
