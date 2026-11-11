import { Check, ChevronLeft, ChevronRight, Eye, EyeOff } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError, type AiMode, type DefaultStructure, type SetupPayload } from "../api";
import { Button, ErrorBanner, Field, VillageCrest, aiModeLabel, cx } from "../components/ui";

export interface WizardForm {
  villageName: string;
  chairmanName: string;
  username: string;
  password: string;
  confirmPassword: string;
  timezone: string;
  aiMode: AiMode;
  ollamaUrl: string;
  anthropicApiKey: string;
  defaultStructure: DefaultStructure;
}

type FieldName = keyof WizardForm;
type Errors = Partial<Record<FieldName, string>>;

export const INITIAL_FORM: WizardForm = {
  villageName: "",
  chairmanName: "",
  username: "",
  password: "",
  confirmPassword: "",
  timezone: "Asia/Dhaka",
  aiMode: "demo",
  ollamaUrl: "http://127.0.0.1:11434",
  anthropicApiKey: "",
  defaultStructure: "standard",
};

const STEPS: Array<{ title: string; summary: string; fields: FieldName[] }> = [
  { title: "Village & Chairman", summary: "Name your village", fields: ["villageName", "chairmanName"] },
  { title: "Admin account", summary: "Your login", fields: ["username", "password", "confirmPassword"] },
  { title: "Timezone", summary: "Village clock", fields: ["timezone"] },
  { title: "AI mode", summary: "Demo, local or cloud", fields: ["aiMode", "ollamaUrl", "anthropicApiKey"] },
  { title: "Default structure", summary: "Starting layout", fields: ["defaultStructure"] },
  { title: "Review & Finish", summary: "Check and create", fields: [] },
];
const LAST_STEP = STEPS.length - 1;

/** Server field names (snake_case) → wizard field names. */
const SERVER_FIELDS: Record<string, FieldName> = {
  village_name: "villageName",
  chairman_name: "chairmanName",
  username: "username",
  password: "password",
  timezone: "timezone",
  ai_mode: "aiMode",
  ollama_url: "ollamaUrl",
  anthropic_api_key: "anthropicApiKey",
  default_structure: "defaultStructure",
};

const USERNAME_RE = /^[a-z0-9][a-z0-9_.-]{2,31}$/i;
const API_KEY_RE = /^[A-Za-z0-9_-]{20,256}$/;
const MIN_PASSWORD = 10;

export function timezoneOptions(): string[] {
  let zones: string[] = [];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    zones = [];
  }
  return [...new Set(["Asia/Dhaka", "UTC", ...zones])].sort((a, b) => a.localeCompare(b));
}

function isLocalHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (
      url.protocol === "http:" &&
      ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    );
  } catch {
    return false;
  }
}

export function passwordStrength(password: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (password.length === 0) {
    return { score: 0, label: "" };
  }
  if (password.length < MIN_PASSWORD) {
    const missing = MIN_PASSWORD - password.length;
    return { score: 1, label: `Too short — ${missing} more character${missing === 1 ? "" : "s"} needed` };
  }
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(password)).length;
  if (password.length >= 20 || (password.length >= 16 && variety >= 3)) {
    return { score: 4, label: "Strong" };
  }
  if (password.length >= 14 || variety >= 3) {
    return { score: 3, label: "Good" };
  }
  return { score: 2, label: "Fair — a longer passphrase is stronger" };
}

export function validateStep(step: number, form: WizardForm, timezones: string[]): Errors {
  const errors: Errors = {};
  switch (step) {
    case 0:
      if (!form.villageName.trim()) errors.villageName = "Enter a village name.";
      else if (form.villageName.trim().length > 80) errors.villageName = "Keep the village name under 80 characters.";
      if (!form.chairmanName.trim()) errors.chairmanName = "Enter the chairman's name.";
      else if (form.chairmanName.trim().length > 80) errors.chairmanName = "Keep the name under 80 characters.";
      break;
    case 1:
      if (!USERNAME_RE.test(form.username.trim())) {
        errors.username = "Use 3–32 characters: letters, digits, dot, underscore or hyphen.";
      }
      if (form.password.length < MIN_PASSWORD) {
        errors.password = `The password needs at least ${MIN_PASSWORD} characters.`;
      } else if (form.password.length > 128) {
        errors.password = "The password can be at most 128 characters.";
      }
      if (form.confirmPassword !== form.password) {
        errors.confirmPassword = "Passwords do not match.";
      }
      break;
    case 2:
      if (!timezones.includes(form.timezone)) errors.timezone = "Choose a timezone from the list.";
      break;
    case 3:
      if (form.aiMode === "ollama" && !isLocalHttpUrl(form.ollamaUrl.trim())) {
        errors.ollamaUrl = "Enter an http:// URL on this PC, for example http://127.0.0.1:11434";
      }
      if (form.aiMode === "anthropic" && !API_KEY_RE.test(form.anthropicApiKey.trim())) {
        errors.anthropicApiKey = "Paste your Anthropic API key (letters, digits, - and _ only).";
      }
      break;
    default:
      break;
  }
  return errors;
}

export function buildPayload(form: WizardForm): SetupPayload {
  return {
    village_name: form.villageName.trim(),
    chairman_name: form.chairmanName.trim(),
    username: form.username.trim().toLowerCase(),
    password: form.password,
    timezone: form.timezone,
    ai_mode: form.aiMode,
    // provider details are only sent for the mode that was actually chosen
    ollama_url: form.aiMode === "ollama" ? form.ollamaUrl.trim() : null,
    anthropic_api_key: form.aiMode === "anthropic" ? form.anthropicApiKey.trim() : null,
    default_structure: form.defaultStructure,
  };
}

interface ChoiceProps<T extends string> {
  name: string;
  value: T;
  current: T;
  title: string;
  tag?: string;
  description: ReactNode;
  onSelect: (value: T) => void;
  children?: ReactNode;
}

function Choice<T extends string>({ name, value, current, title, tag, description, onSelect, children }: ChoiceProps<T>) {
  const selected = value === current;
  return (
    <div
      className={cx(
        "rounded-xl border transition",
        selected ? "border-lantern-400/70 bg-lantern-400/[0.06]" : "border-night-600 hover:border-night-500",
      )}
    >
      <label className="flex cursor-pointer items-start gap-3 p-4">
        <input
          type="radio"
          name={name}
          value={value}
          checked={selected}
          onChange={() => onSelect(value)}
          className="mt-1 size-4 accent-lantern-400"
        />
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-mist-50">{title}</span>
            {tag && (
              <span className="rounded border border-night-500 px-1.5 py-px font-mono text-[10px] uppercase tracking-wider text-mist-400">
                {tag}
              </span>
            )}
          </span>
          <span className="mt-1 block text-[13px] leading-relaxed text-mist-400">{description}</span>
        </span>
      </label>
      {selected && children && <div className="border-t border-night-700 px-4 pb-2 pt-4">{children}</div>}
    </div>
  );
}

function ReviewRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-t border-night-700/70 py-2.5 first:border-t-0">
      <dt className="text-sm text-mist-400">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm font-medium text-mist-50">{children}</dd>
    </div>
  );
}

export default function SetupWizard({ onComplete }: { onComplete: () => Promise<void> | void }) {
  const [form, setForm] = useState<WizardForm>(INITIAL_FORM);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const timezones = useMemo(timezoneOptions, []);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  function set<K extends FieldName>(field: K, value: WizardForm[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      if (!(field in current)) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  function goNext() {
    const found = validateStep(step, form, timezones);
    setErrors(found);
    if (Object.keys(found).length === 0) {
      setServerError(null);
      setStep((current) => Math.min(current + 1, LAST_STEP));
    }
  }

  function goBack() {
    setErrors({});
    setStep((current) => Math.max(current - 1, 0));
  }

  async function finish() {
    // re-check every step: nothing invalid may be submitted
    for (let index = 0; index < LAST_STEP; index += 1) {
      const found = validateStep(index, form, timezones);
      if (Object.keys(found).length > 0) {
        setErrors(found);
        setStep(index);
        return;
      }
    }
    setBusy(true);
    setServerError(null);
    try {
      await api.setup(buildPayload(form));
      await onComplete();
    } catch (cause) {
      setBusy(false);
      if (cause instanceof ApiError) {
        const mapped: Errors = {};
        for (const [serverField, message] of Object.entries(cause.fieldErrors)) {
          const field = SERVER_FIELDS[serverField];
          if (field) mapped[field] = message;
        }
        const mappedFields = Object.keys(mapped) as FieldName[];
        if (mappedFields.length > 0) {
          setErrors(mapped);
          const target = STEPS.findIndex((candidate) => candidate.fields.some((field) => mappedFields.includes(field)));
          if (target >= 0) setStep(target);
          setServerError("The server rejected some values. Fix the highlighted fields and try again.");
        } else {
          setServerError(cause.message);
        }
      } else {
        setServerError("Setup failed unexpectedly. Check ./village logs and try again.");
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (step === LAST_STEP) void finish();
    else goNext();
  }

  const strength = passwordStrength(form.password);
  const current = STEPS[step]!;
  const describedBy = (id: string) => `${id}-note`;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col justify-center px-4 py-10">
      <header className="mb-8 flex items-center gap-4">
        <VillageCrest size={48} />
        <div>
          <p className="eyebrow">First-run setup</p>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-50">Found your AI Agent Village</h1>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
        <ol aria-label="Setup steps" className="flex gap-2 overflow-x-auto lg:flex-col lg:gap-1">
          {STEPS.map((item, index) => {
            const done = index < step;
            const active = index === step;
            return (
              <li
                key={item.title}
                aria-current={active ? "step" : undefined}
                className={cx(
                  "flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5",
                  active && "bg-night-800 shadow-[inset_2px_0_0_var(--color-lantern-400)]",
                )}
              >
                <span
                  className={cx(
                    "grid size-7 shrink-0 place-items-center rounded-full border font-mono text-xs",
                    done && "border-paddy-500/60 bg-paddy-500/15 text-paddy-300",
                    active && "border-lantern-400 text-lantern-300",
                    !done && !active && "border-night-600 text-mist-500",
                  )}
                >
                  {done ? <Check size={13} aria-hidden="true" /> : index + 1}
                </span>
                <span className="hidden leading-tight lg:block">
                  <span className={cx("block text-sm", active ? "font-semibold text-mist-50" : "text-mist-300")}>{item.title}</span>
                  <span className="block text-xs text-mist-500">{item.summary}</span>
                </span>
              </li>
            );
          })}
        </ol>

        <form onSubmit={handleSubmit} noValidate className="panel flex min-h-[30rem] flex-col p-6 sm:p-8">
          <p className="eyebrow">
            Step {step + 1} of {STEPS.length}
          </p>
          <h2 ref={headingRef} tabIndex={-1} className="mt-1 text-xl font-semibold text-mist-50 outline-none">
            {current.title}
          </h2>

          <div key={step} className="mt-6 flex-1 animate-rise space-y-4">
            {serverError && <ErrorBanner>{serverError}</ErrorBanner>}

            {step === 0 && (
              <>
                <Field id="villageName" label="Village name" hint="Shown at the top of your control center." error={errors.villageName}>
                  <input
                    id="villageName"
                    className="input"
                    autoFocus
                    maxLength={80}
                    value={form.villageName}
                    aria-invalid={Boolean(errors.villageName)}
                    aria-describedby={describedBy("villageName")}
                    onChange={(event) => set("villageName", event.target.value)}
                  />
                </Field>
                <Field id="chairmanName" label="Chairman name" hint="That is you — the owner and only administrator." error={errors.chairmanName}>
                  <input
                    id="chairmanName"
                    className="input"
                    maxLength={80}
                    autoComplete="name"
                    value={form.chairmanName}
                    aria-invalid={Boolean(errors.chairmanName)}
                    aria-describedby={describedBy("chairmanName")}
                    onChange={(event) => set("chairmanName", event.target.value)}
                  />
                </Field>
              </>
            )}

            {step === 1 && (
              <>
                <Field id="username" label="Username" hint="3–32 characters. Saved in lowercase." error={errors.username}>
                  <input
                    id="username"
                    className="input"
                    autoFocus
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    value={form.username}
                    aria-invalid={Boolean(errors.username)}
                    aria-describedby={describedBy("username")}
                    onChange={(event) => set("username", event.target.value)}
                  />
                </Field>
                <Field
                  id="password"
                  label="Password"
                  error={errors.password}
                  hint={
                    strength.score === 0 ? (
                      `At least ${MIN_PASSWORD} characters. A long passphrase works well.`
                    ) : (
                      <span data-testid="password-strength">Strength: {strength.label}</span>
                    )
                  }
                >
                  <div className="relative">
                    <input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      className="input pr-11"
                      autoComplete="new-password"
                      value={form.password}
                      aria-invalid={Boolean(errors.password)}
                      aria-describedby={describedBy("password")}
                      onChange={(event) => set("password", event.target.value)}
                    />
                    <button
                      type="button"
                      aria-label={showPassword ? "Hide passwords" : "Show passwords"}
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword((value) => !value)}
                      className="absolute inset-y-0 right-0 grid w-11 place-items-center text-mist-400 hover:text-mist-50"
                    >
                      {showPassword ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                    </button>
                  </div>
                  <div className="mt-2 grid grid-cols-4 gap-1.5" aria-hidden="true">
                    {[1, 2, 3, 4].map((level) => (
                      <span
                        key={level}
                        className={cx(
                          "h-1 rounded-full transition-colors",
                          strength.score >= level
                            ? strength.score === 1
                              ? "bg-clay-400"
                              : strength.score === 2
                                ? "bg-lantern-400"
                                : "bg-paddy-400"
                            : "bg-night-700",
                        )}
                      />
                    ))}
                  </div>
                </Field>
                <Field id="confirmPassword" label="Confirm password" error={errors.confirmPassword}>
                  <input
                    id="confirmPassword"
                    type={showPassword ? "text" : "password"}
                    className="input"
                    autoComplete="new-password"
                    value={form.confirmPassword}
                    aria-invalid={Boolean(errors.confirmPassword)}
                    aria-describedby={describedBy("confirmPassword")}
                    onChange={(event) => set("confirmPassword", event.target.value)}
                  />
                </Field>
              </>
            )}

            {step === 2 && (
              <Field
                id="timezone"
                label="Timezone"
                hint="Schedules, deadlines and reports will use this timezone."
                error={errors.timezone}
              >
                <select
                  id="timezone"
                  className="input"
                  autoFocus
                  value={form.timezone}
                  aria-invalid={Boolean(errors.timezone)}
                  aria-describedby={describedBy("timezone")}
                  onChange={(event) => set("timezone", event.target.value)}
                >
                  {timezones.map((zone) => (
                    <option key={zone} value={zone}>
                      {zone}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            {step === 3 && (
              <fieldset className="space-y-3">
                <legend className="mb-3 text-sm text-mist-300">
                  You can finish setup without any AI provider. Provider connections are not tested here.
                </legend>
                <Choice
                  name="aiMode"
                  value="demo"
                  current={form.aiMode}
                  title="Demo Mode"
                  tag="recommended"
                  description="No AI provider and no API key needed."
                  onSelect={(value) => set("aiMode", value)}
                />
                <Choice
                  name="aiMode"
                  value="ollama"
                  current={form.aiMode}
                  title="Local AI (Ollama)"
                  tag="not tested"
                  description="Use an Ollama server that is already installed and running on this PC."
                  onSelect={(value) => set("aiMode", value)}
                >
                  <Field
                    id="ollamaUrl"
                    label="Ollama URL"
                    hint="Must be an http:// address on this PC. It is saved, not tested."
                    error={errors.ollamaUrl}
                  >
                    <input
                      id="ollamaUrl"
                      className="input font-mono text-sm"
                      inputMode="url"
                      spellCheck={false}
                      value={form.ollamaUrl}
                      aria-invalid={Boolean(errors.ollamaUrl)}
                      aria-describedby={describedBy("ollamaUrl")}
                      onChange={(event) => set("ollamaUrl", event.target.value)}
                    />
                  </Field>
                </Choice>
                <Choice
                  name="aiMode"
                  value="anthropic"
                  current={form.aiMode}
                  title="Cloud AI (Anthropic)"
                  tag="not tested"
                  description="Use your own Anthropic API key. A Claude subscription login cannot be used as an API key."
                  onSelect={(value) => set("aiMode", value)}
                >
                  <Field
                    id="anthropicApiKey"
                    label="Anthropic API key (saved, not tested)"
                    hint="Stored only in data/.env on this PC — never in the database. It is saved, not tested."
                    error={errors.anthropicApiKey}
                  >
                    <input
                      id="anthropicApiKey"
                      type="password"
                      className="input font-mono text-sm"
                      autoComplete="off"
                      spellCheck={false}
                      value={form.anthropicApiKey}
                      aria-invalid={Boolean(errors.anthropicApiKey)}
                      aria-describedby={describedBy("anthropicApiKey")}
                      onChange={(event) => set("anthropicApiKey", event.target.value)}
                    />
                  </Field>
                </Choice>
              </fieldset>
            )}

            {step === 4 && (
              <fieldset className="space-y-3">
                <legend className="mb-3 text-sm text-mist-300">
                  Your choice is saved now. The structure itself is generated in M2 — nothing is created yet.
                </legend>
                <Choice
                  name="defaultStructure"
                  value="standard"
                  current={form.defaultStructure}
                  title="Standard village"
                  description="Six Upazila templates — Study, Business, Career & Job Preparation, Research, Project Development and Personal Management — each with its Unions, 9 Wards per Union and an Office per Ward."
                  onSelect={(value) => set("defaultStructure", value)}
                />
                <Choice
                  name="defaultStructure"
                  value="empty"
                  current={form.defaultStructure}
                  title="Empty village"
                  description="Start with nothing and add Upazilas, Unions and Wards yourself."
                  onSelect={(value) => set("defaultStructure", value)}
                />
              </fieldset>
            )}

            {step === LAST_STEP && (
              <>
                <dl className="rounded-xl border border-night-700 bg-night-900/60 px-4">
                  <ReviewRow label="Village name">{form.villageName.trim()}</ReviewRow>
                  <ReviewRow label="Chairman">{form.chairmanName.trim()}</ReviewRow>
                  <ReviewRow label="Username">{form.username.trim().toLowerCase()}</ReviewRow>
                  <ReviewRow label="Password">{"•".repeat(Math.min(form.password.length, 16))} (hidden)</ReviewRow>
                  <ReviewRow label="Timezone">{form.timezone}</ReviewRow>
                  <ReviewRow label="AI mode">{aiModeLabel(form.aiMode)}</ReviewRow>
                  {form.aiMode === "ollama" && <ReviewRow label="Ollama URL">{form.ollamaUrl.trim()}</ReviewRow>}
                  {form.aiMode === "anthropic" && <ReviewRow label="Anthropic API key">provided (hidden) — saved, not tested</ReviewRow>}
                  <ReviewRow label="Default structure">
                    {form.defaultStructure === "standard" ? "Standard village" : "Empty village"} (generated in M2)
                  </ReviewRow>
                </dl>
                <p className="text-sm text-mist-400">
                  Finishing creates the village and your admin account, and signs you in. Setup can only be run once.
                </p>
              </>
            )}
          </div>

          <div className="mt-8 flex items-center justify-between gap-3 border-t border-night-700 pt-5">
            <Button
              variant="ghost"
              onClick={goBack}
              disabled={step === 0 || busy}
              icon={<ChevronLeft size={16} aria-hidden="true" />}
            >
              Back
            </Button>
            {step === LAST_STEP ? (
              <Button type="submit" busy={busy}>
                Finish setup
              </Button>
            ) : (
              <Button type="submit">
                Next
                <ChevronRight size={16} aria-hidden="true" />
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
