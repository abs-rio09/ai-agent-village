import { ArrowLeft, Check, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage, type Approval, type ApprovalStatus } from "../api";
import { refreshPendingApprovals } from "../approvalCount";
import { AgentAvatar, Badge, formatTime } from "../components/agents";
import { Dialog } from "../components/Dialog";
import { EmptyState, PageHeader } from "../components/org";
import { Button, ErrorBanner, cx } from "../components/ui";

// Approval Center: an agent asked to use a SENSITIVE tool. Nothing happens until the Chairman
// decides here. Every check is on the server; this page only shows and sends the decision.

export const POLL_MS = 5000;
const NOTE_MAX = 500;

type Filter = ApprovalStatus | "ALL";
const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: "PENDING", label: "Pending" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELLED", label: "Withdrawn" },
  { value: "ALL", label: "All" },
];

const STATUS_TONE: Record<ApprovalStatus, "warn" | "good" | "bad" | "muted"> = {
  PENDING: "warn",
  APPROVED: "good",
  REJECTED: "bad",
  CANCELLED: "muted",
};
const STATUS_LABEL: Record<ApprovalStatus, string> = {
  PENDING: "pending",
  APPROVED: "approved",
  REJECTED: "rejected",
  CANCELLED: "withdrawn",
};

function decidedBy(value: string | null): string {
  if (!value) return "—";
  if (value === "system") return "the system (the task ended first)";
  return value.startsWith("chairman:") ? `Chairman (${value.slice("chairman:".length)})` : value;
}

function Row({ label, children, strong = false }: { label: string; children: React.ReactNode; strong?: boolean }) {
  return (
    <div className="border-t border-night-700/70 py-2.5 sm:grid sm:grid-cols-[11rem_1fr] sm:gap-4">
      <dt className="text-xs uppercase tracking-wider text-mist-400">{label}</dt>
      <dd className={cx("mt-1 min-w-0 break-words text-sm sm:mt-0", strong ? "font-medium text-mist-50" : "text-mist-100")}>{children}</dd>
    </div>
  );
}

interface CardProps {
  approval: Approval;
  timezone?: string;
  onDecide: (approval: Approval, decision: "approve" | "reject") => void;
}

/** One request with every field of docs/SPEC.md §8F. */
function ApprovalCard({ approval, timezone, onDecide }: CardProps) {
  const isPending = approval.status === "PENDING";
  return (
    <article className="panel p-5" aria-label={`Approval request ${approval.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {approval.agent && <AgentAvatar avatarKey={approval.agent.avatar_key} size={40} />}
          <div className="min-w-0">
            <p className="eyebrow">Request #{approval.id}</p>
            <p className="truncate text-sm font-semibold text-mist-50">{approval.tool_name}</p>
          </div>
        </div>
        <Badge tone={STATUS_TONE[approval.status]} testId="approval-status">
          {STATUS_LABEL[approval.status]}
        </Badge>
      </div>

      <dl className="mt-4">
        <Row label="Requesting agent">
          {approval.agent ? (
            <>
              <Link to={`/agents/profile?id=${approval.agent.id}`} className="font-medium text-lantern-300 underline-offset-4 hover:underline">
                {approval.agent.display_name}
              </Link>{" "}
              <span className="text-mist-400">· {approval.agent.role}</span>
            </>
          ) : (
            "an agent that no longer exists"
          )}
        </Row>
        <Row label="Requested action" strong>
          {approval.action}
        </Row>
        <Row label="Reason">{approval.reason}</Row>
        <Row label="Tool">
          {approval.tool_name} <span className="font-mono text-xs text-mist-400">({approval.tool_key})</span>
        </Row>
        <Row label="Expected changes">{approval.expected_changes}</Row>
        <Row label="Risk information">
          <span className="mr-2 rounded border border-clay-500/40 px-1 font-mono text-[10px] uppercase tracking-wider text-clay-300">
            {approval.risk}
          </span>
          <span className="text-clay-300">{approval.risk_info}</span>
        </Row>
        <Row label="Task">
          <Link to={`/tasks?id=${approval.task_id}`} className="text-lantern-300 underline-offset-4 hover:underline">
            #{approval.task_id} {approval.task_title}
          </Link>{" "}
          {approval.task_status && <span className="font-mono text-[11px] text-mist-400">{approval.task_status.replace("_", " ")}</span>}
        </Row>
        <Row label="Requested">{formatTime(approval.created_at, timezone)}</Row>
        {!isPending && (
          <>
            <Row label="Decision">
              {STATUS_LABEL[approval.status]} by {decidedBy(approval.decided_by)}, {formatTime(approval.decided_at, timezone)}
              {approval.decision_note && <span className="block text-mist-300">Note: {approval.decision_note}</span>}
            </Row>
            {approval.status === "APPROVED" && (
              <Row label="Result">{approval.result ?? "The task has not carried it out yet."}</Row>
            )}
          </>
        )}
      </dl>

      {isPending && (
        <div className="mt-4 flex flex-wrap justify-end gap-2 mobile:grid mobile:grid-cols-2">
          <Button variant="danger" icon={<X size={16} aria-hidden="true" />} onClick={() => onDecide(approval, "reject")}>
            Reject
          </Button>
          <Button icon={<Check size={16} aria-hidden="true" />} onClick={() => onDecide(approval, "approve")}>
            Approve
          </Button>
        </div>
      )}
    </article>
  );
}

interface ConfirmProps {
  approval: Approval;
  decision: "approve" | "reject";
  onDone: () => Promise<void>;
  onClose: () => void;
}

/** The confirm step: say again what is decided, take an optional note, send it once. */
function ConfirmDecision({ approval, decision, onDone, onClose }: ConfirmProps) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approving = decision === "approve";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.decideApproval(approval.id, decision, note.trim());
      await onDone();
      onClose();
    } catch (cause) {
      // for example 409: it was decided on another device, or the task was cancelled
      setError(errorMessage(cause, "The decision could not be saved."));
      setBusy(false);
      await onDone();
    }
  }

  return (
    <Dialog title={approving ? "Approve this request?" : "Reject this request?"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <p className="text-sm leading-relaxed text-mist-300">
          <strong className="font-semibold text-mist-50">{approval.agent?.display_name ?? "An agent"}</strong> wants to:{" "}
          <span className="text-mist-50">{approval.action}</span>
        </p>
        <p className="text-sm leading-relaxed text-mist-300">
          {approving
            ? "The task continues. No connector exists yet, so the approval is only recorded — nothing is sent, deleted, paid or published."
            : "Nothing is done and the task fails with “rejected by Chairman”."}
        </p>
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div>
          <label htmlFor="decision-note" className="mb-1.5 block text-sm font-medium text-mist-100">
            Note (optional)
          </label>
          <textarea
            id="decision-note"
            className="input min-h-16"
            maxLength={NOTE_MAX}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant={approving ? "primary" : "danger"} busy={busy} data-autofocus>
            {approving ? "Yes, approve" : "Yes, reject"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export default function Approvals({ timezone, pollMs = POLL_MS }: { timezone?: string; pollMs?: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = Number(searchParams.get("id")) || null;
  const filter = (FILTERS.find((item) => item.value === searchParams.get("status"))?.value ?? "PENDING") as Filter;
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<{ approval: Approval; decision: "approve" | "reject" } | null>(null);

  const reload = useCallback(async () => {
    try {
      const list = selectedId !== null ? [await api.approval(selectedId)] : await api.approvals(filter === "ALL" ? null : filter);
      setApprovals(list);
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause, "Could not load the approval requests."));
    }
    void refreshPendingApprovals();
  }, [filter, selectedId]);

  useEffect(() => {
    setApprovals(null);
    void reload();
    const timer = window.setInterval(() => void reload(), pollMs); // new requests appear without a reload
    return () => window.clearInterval(timer);
  }, [reload, pollMs]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Approval Center"
        intro="Sensitive actions never run by themselves. An agent that wants to send an external message, delete a file, spend money or publish something asks here first, and its task waits for your decision."
      />
      <p role="note" className="rounded-xl border border-lantern-500/30 bg-lantern-500/10 px-4 py-3 text-sm text-lantern-200">
        No external connector exists yet. An approved request is only <strong className="font-semibold">recorded</strong>: nothing is
        really sent, deleted, paid or published.
      </p>
      {error && <ErrorBanner>{error}</ErrorBanner>}

      {selectedId !== null ? (
        <Link
          to="/approvals"
          className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-night-600 px-4 text-sm font-semibold text-mist-100"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          All approval requests
        </Link>
      ) : (
        <div role="tablist" aria-label="Filter by status" className="flex flex-wrap gap-2">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={filter === item.value}
              onClick={() => setSearchParams(item.value === "PENDING" ? {} : { status: item.value })}
              className={cx(
                "min-h-11 rounded-xl border px-4 text-sm font-medium transition sm:min-h-9",
                filter === item.value
                  ? "border-lantern-400/60 bg-lantern-500/10 text-lantern-200"
                  : "border-night-600 text-mist-300 hover:border-night-500 hover:text-mist-50",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {approvals === null ? (
        !error && <p className="text-sm text-mist-400">Loading the approval requests…</p>
      ) : approvals.length === 0 ? (
        <EmptyState title={filter === "PENDING" ? "Nothing is waiting for you" : "No requests here"}>
          <ShieldCheck size={28} aria-hidden="true" className="text-paddy-400" />
          <p>
            {filter === "PENDING"
              ? "When an agent asks to use a sensitive tool, the request appears here and its task waits."
              : "No approval request has this status."}
          </p>
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              timezone={timezone}
              onDecide={(target, decision) => setDeciding({ approval: target, decision })}
            />
          ))}
        </div>
      )}

      {deciding && (
        <ConfirmDecision approval={deciding.approval} decision={deciding.decision} onDone={reload} onClose={() => setDeciding(null)} />
      )}
    </div>
  );
}
