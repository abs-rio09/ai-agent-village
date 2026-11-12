import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { errorMessage } from "../api";
import { Button, ErrorBanner, Field } from "./ui";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])';

interface DialogProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * Modal dialog: labelled, closes on Escape or backdrop click, keeps Tab inside, restores focus.
 *
 * It is rendered in a portal on <body>. The page content sits inside an animated (transformed)
 * wrapper, and a transform turns `position: fixed` into "fixed to that wrapper" — rendered in
 * place, the backdrop would cover only the page area instead of the whole window.
 */
export function Dialog({ title, onClose, children }: DialogProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = panel.current?.querySelector<HTMLElement>("[data-autofocus]") ?? panel.current;
    first?.focus();
    return () => previous?.focus();
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" onKeyDown={handleKeyDown}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="panel relative w-full max-w-lg animate-rise bg-night-850 p-6 outline-none"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-lg font-semibold text-mist-50">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close dialog"
            onClick={onClose}
            className="-mr-1 -mt-1 rounded-lg p-1.5 text-mist-400 transition hover:bg-night-700 hover:text-mist-50"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

interface ConfirmDeleteProps {
  /** "Upazila", "Union" or "Ward". */
  kind: string;
  name: string;
  /** What disappears together with it, e.g. "5 Unions, 45 Wards and 45 Offices". */
  consequence: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

/** Destructive confirmation: the Delete button stays disabled until the exact name is typed. */
export function ConfirmDeleteDialog({ kind, name, consequence, onConfirm, onClose }: ConfirmDeleteProps) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matches = typed.trim() === name;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!matches || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (cause) {
      setError(errorMessage(cause, "The deletion failed."));
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Delete ${kind}`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <p className="text-sm leading-relaxed text-mist-300">
          This permanently deletes the {kind} <strong className="font-semibold text-mist-50">{name}</strong>
          {consequence ? ` together with ${consequence}` : ""}. It cannot be undone.
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <Field id="confirm-delete-name" label={`Type the name to confirm: ${name}`}>
          <input
            id="confirm-delete-name"
            data-autofocus
            className="input"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            aria-describedby="confirm-delete-name-note"
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={!matches} busy={busy}>
            Delete {kind}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
