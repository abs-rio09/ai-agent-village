import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, errorMessage, type AgentOptions, type AgentTemplate } from "../api";
import { CatalogChecklist, EnforcementNote, INSTRUCTIONS_MAX, OfficePicker } from "../components/agents";
import { RobotAvatar, robotRoleFor } from "../components/robots";
import { Breadcrumbs, DESCRIPTION_MAX, NAME_MAX, PageHeader, useOrgTree, validateName } from "../components/org";
import { Button, ErrorBanner, Field, cx } from "../components/ui";

// "New Agent" wizard (docs/SPEC.md §6): template → name → Office → responsibilities → tools and
// permissions → save and activate. Nothing is written until the last step.

const STEPS = ["Template", "Name", "Office", "Responsibilities", "Tools & permissions"];
const LAST_STEP = STEPS.length - 1;

interface Form {
  templateId: number | null;
  name: string;
  officeId: number | null;
  role: string;
  description: string;
  instructions: string;
  tools: string[];
  permissions: string[];
}

const EMPTY: Form = { templateId: null, name: "", officeId: null, role: "", description: "", instructions: "", tools: [], permissions: [] };

function problemOf(step: number, form: Form): string | null {
  switch (step) {
    case 0:
      return form.templateId === null ? "Choose a template." : null;
    case 1:
      return validateName(form.name, "a name for the agent");
    case 2:
      return form.officeId === null ? "Choose the Office the agent will work in." : null;
    case 3:
      return validateName(form.role, "a role");
    default:
      return null;
  }
}

export default function AgentWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { tree, error: treeError } = useOrgTree();
  const [templates, setTemplates] = useState<AgentTemplate[] | null>(null);
  const [options, setOptions] = useState<AgentOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(EMPTY);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.agentTemplates(), api.agentOptions()])
      .then(([templateList, optionList]) => {
        if (cancelled) return;
        setTemplates(templateList);
        setOptions(optionList);
      })
      .catch((cause: unknown) => !cancelled && setLoadError(errorMessage(cause, "Could not load the agent templates.")));
    return () => {
      cancelled = true;
    };
  }, []);

  // Opened from an Upazila's agent list (?upazila=): start with that Upazila's first Ward office.
  const preferredUpazila = Number(searchParams.get("upazila")) || null;
  useEffect(() => {
    if (!tree || preferredUpazila === null) return;
    const first = tree.upazilas
      .find((item) => item.id === preferredUpazila)
      ?.unions.flatMap((union) => union.wards)
      .find((ward) => ward.office);
    if (first?.office) setForm((current) => (current.officeId === null ? { ...current, officeId: first.office!.id } : current));
  }, [tree, preferredUpazila]);

  const template = templates?.find((item) => item.id === form.templateId) ?? null;

  function change(patch: Partial<Form>) {
    setForm((current) => ({ ...current, ...patch }));
    setProblem(null);
  }

  /** Choosing a template copies its defaults into the form (they stay editable). */
  function chooseTemplate(chosen: AgentTemplate) {
    setForm((current) => ({
      ...current,
      templateId: chosen.id,
      // keep a name the Chairman typed; replace an empty one or the previous template's name
      name: current.name.trim() === "" || current.name === template?.name ? chosen.name : current.name,
      role: chosen.role,
      description: chosen.description,
      instructions: chosen.default_instructions,
      tools: chosen.default_tools,
      permissions: chosen.default_permissions,
    }));
    setProblem(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = problemOf(step, form);
    if (found) {
      setProblem(found);
      return;
    }
    if (step < LAST_STEP) {
      setStep(step + 1);
      return;
    }
    const firstBad = STEPS.findIndex((_title, index) => problemOf(index, form) !== null);
    if (firstBad !== -1 || form.templateId === null || form.officeId === null) {
      setStep(Math.max(firstBad, 0));
      setProblem(problemOf(Math.max(firstBad, 0), form));
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const agent = await api.createAgent({
        template_id: form.templateId,
        display_name: form.name.trim(),
        office_id: form.officeId,
        role: form.role.trim(),
        description: form.description.trim(),
        system_instructions: form.instructions.trim(),
        allowed_tools: form.tools,
        permissions: form.permissions,
        activate: true,
      });
      navigate(`/agents/profile?id=${agent.id}`);
    } catch (cause) {
      setProblem(errorMessage(cause, "The agent could not be created."));
      setBusy(false);
    }
  }

  const ready = templates !== null && options !== null && tree !== null;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Agent Management", to: "/agents" }, { label: "New agent" }]} />
      <PageHeader
        eyebrow="Agents"
        title="New agent"
        intro="Five short steps. The template fills in sensible defaults; you can change every one of them here or later on the agent's profile."
      />
      {(loadError || treeError) && <ErrorBanner>{loadError ?? treeError}</ErrorBanner>}

      {!ready ? (
        !(loadError || treeError) && <p className="text-sm text-mist-400">Loading the templates…</p>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="panel p-5 sm:p-6">
          <ol aria-label="Steps" className="flex flex-wrap gap-2">
            {STEPS.map((title, index) => (
              <li
                key={title}
                aria-current={index === step ? "step" : undefined}
                className={cx(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
                  index === step
                    ? "border-lantern-400/70 bg-lantern-500/10 text-lantern-200"
                    : index < step
                      ? "border-paddy-500/40 text-paddy-300"
                      : "border-night-600 text-mist-500",
                )}
              >
                <span className="font-mono">{index < step ? <Check size={12} aria-hidden="true" /> : index + 1}</span>
                {title}
              </li>
            ))}
          </ol>

          <h2 className="mt-6 text-lg font-semibold text-mist-50">
            Step {step + 1} of {STEPS.length}: {STEPS[step]}
          </h2>

          <div key={step} className="mt-4 animate-rise space-y-4">
            {step === 0 && (
              <div role="radiogroup" aria-label="Agent template" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {templates.map((item) => (
                  <label
                    key={item.id}
                    className={cx(
                      "flex cursor-pointer gap-3 rounded-xl border p-3 transition",
                      item.id === form.templateId ? "border-lantern-400/80 bg-lantern-500/10" : "border-night-700 hover:border-night-500",
                    )}
                  >
                    <input
                      type="radio"
                      name="agent-template"
                      className="sr-only"
                      checked={item.id === form.templateId}
                      onChange={() => chooseTemplate(item)}
                    />
                    <RobotAvatar role={robotRoleFor(item.key)} size={44} />
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-mist-50">{item.name}</span>
                      <span className="block text-xs leading-snug text-mist-400">{item.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}

            {step === 1 && (
              <Field id="agent-name" label="Agent name" hint={`Shown on the agent's card and in task reports. Template: ${template?.name ?? "—"}.`}>
                <input
                  id="agent-name"
                  autoFocus
                  className="input max-w-md"
                  maxLength={NAME_MAX}
                  value={form.name}
                  onChange={(event) => change({ name: event.target.value })}
                  aria-describedby="agent-name-note"
                />
              </Field>
            )}

            {step === 2 && (
              <>
                {tree.upazilas.length === 0 && (
                  <p className="text-sm text-mist-300">
                    There are no Upazilas yet, so only Central Administration can be chosen.{" "}
                    <Link to="/upazilas" className="font-medium text-lantern-300 underline-offset-4 hover:underline">
                      Create an Upazila
                    </Link>{" "}
                    to give agents a Ward office.
                  </p>
                )}
                <OfficePicker
                  tree={tree}
                  value={form.officeId}
                  onChange={(officeId) => change({ officeId })}
                  idPrefix="agent-office"
                />
              </>
            )}

            {step === 3 && (
              <>
                <Field id="agent-role" label="Role">
                  <input
                    id="agent-role"
                    autoFocus
                    className="input max-w-md"
                    maxLength={NAME_MAX}
                    value={form.role}
                    onChange={(event) => change({ role: event.target.value })}
                    aria-describedby="agent-role-note"
                  />
                </Field>
                <Field id="agent-description" label="Responsibilities" hint="What this agent is responsible for. The Central Manager compares these words with a request.">
                  <textarea
                    id="agent-description"
                    className="input min-h-20"
                    maxLength={DESCRIPTION_MAX}
                    value={form.description}
                    onChange={(event) => change({ description: event.target.value })}
                    aria-describedby="agent-description-note"
                  />
                </Field>
                <Field id="agent-instructions" label="System instructions" hint="Saved with the agent. The Demo provider does not read them; a real AI provider will.">
                  <textarea
                    id="agent-instructions"
                    className="input min-h-32"
                    maxLength={INSTRUCTIONS_MAX}
                    value={form.instructions}
                    onChange={(event) => change({ instructions: event.target.value })}
                    aria-describedby="agent-instructions-note"
                  />
                </Field>
              </>
            )}

            {step === LAST_STEP && (
              <>
                <EnforcementNote />
                <CatalogChecklist legend="Allowed tools" items={options.tools} selected={form.tools} onChange={(tools) => change({ tools })} />
                <CatalogChecklist
                  legend="Permissions"
                  items={options.permissions}
                  selected={form.permissions}
                  onChange={(permissions) => change({ permissions })}
                />
              </>
            )}
          </div>

          {problem && (
            <div className="mt-4">
              <ErrorBanner>{problem}</ErrorBanner>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <Button
              variant="ghost"
              icon={<ArrowLeft size={16} aria-hidden="true" />}
              disabled={step === 0 || busy}
              onClick={() => {
                setStep(step - 1);
                setProblem(null);
              }}
            >
              Back
            </Button>
            {step === LAST_STEP ? (
              <Button type="submit" busy={busy} icon={<Check size={16} aria-hidden="true" />}>
                Save &amp; activate
              </Button>
            ) : (
              <Button type="submit" icon={<ArrowRight size={16} aria-hidden="true" />}>
                Next
              </Button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
