"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IconInbox } from "@tabler/icons-react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { failureTypeLabel, humanize } from "@/lib/labels";
import { api, EscalationDetail, EscalationSummary, getStoredRole } from "@/lib/api";

function ReviewPanel({ caseId, onReviewed }: { caseId: string; onReviewed: () => void }) {
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [action, setAction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const isReviewer = getStoredRole() === "reviewer";

  useEffect(() => {
    setDetail(null);
    api
      .getEscalationDetail(caseId)
      .then(setDetail)
      .catch((e) => setError(String(e)));
  }, [caseId]);

  const decide = async (decision: "APPROVE" | "REJECT" | "OVERRIDE") => {
    if (!reason.trim()) {
      setError("A reason is required for every human review decision.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.reviewEscalation(caseId, { decision, reason, action: action || undefined });
      setResult(
        `${response.decision} recorded. Final action: ${response.final_action ?? "none"}. ` +
          (response.gate_approved === null
            ? ""
            : `Policy gate: ${response.gate_approved ? "approved" : "denied"}. `) +
          (response.verification_outcome ? `Verification: ${response.verification_outcome}.` : "")
      );
      onReviewed();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (error && !detail) return <div className="text-[14px] text-[var(--danger-text)]">{error}</div>;
  if (!detail) return <div className="text-[14px] text-[var(--text-muted)]">Loading…</div>;

  return (
    <div className="flex flex-col gap-4 rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-5">
      <div className="grid grid-cols-2 gap-3 text-[14px]">
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Merchant</div>
          <div>{detail.merchant_id}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Amount</div>
          <div className="tabular-nums">
            {detail.currency} {detail.amount}
          </div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Failure code</div>
          <div>{failureTypeLabel(detail.failure_code)}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Payment method</div>
          <div>{detail.payment_method ?? "—"}</div>
        </div>
      </div>

      <div>
        <div className="mb-1 text-[12px] text-[var(--text-secondary)]">Agent proposal history</div>
        <div className="flex flex-col gap-1 text-[13px]">
          {detail.agent_trace.length === 0 && <div className="text-[var(--text-muted)]">No agent proposal on record.</div>}
          {detail.agent_trace.map((a, i) => (
            <div key={i} className="rounded-control border border-[var(--border)] px-3 py-2">
              <div className="font-medium">
                {humanize(a.proposed_action)} — confidence {(a.confidence * 100).toFixed(0)}%, risk{" "}
                {humanize(a.risk_level)}
              </div>
              <div className="text-[var(--text-secondary)]">{a.reason}</div>
              <div className="text-[12px] text-[var(--text-muted)]">
                {a.model_backend} · {new Date(a.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>

      {detail.prior_reviews.length > 0 && (
        <div>
          <div className="mb-1 text-[12px] text-[var(--text-secondary)]">Prior human reviews</div>
          <div className="flex flex-col gap-1 text-[13px]">
            {detail.prior_reviews.map((r, i) => (
              <div key={i} className="rounded-control border border-[var(--border)] px-3 py-2">
                <div className="font-medium">
                  {humanize(r.decision)} by {r.reviewer}
                  {r.final_action ? ` — action: ${humanize(r.final_action)}` : ""}
                </div>
                <div className="text-[var(--text-secondary)]">{r.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isReviewer ? (
        <>
          <div className="flex flex-col gap-2">
            <label className="text-[12px] text-[var(--text-secondary)]">Reason (required, audited)</label>
            <textarea
              className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-2 text-[14px]"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <label className="text-[12px] text-[var(--text-secondary)]">
              Action (required for OVERRIDE; must match the proposal, or be left blank, for APPROVE)
            </label>
            <select
              className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-2 text-[14px]"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              <option value="">(use originally proposed action)</option>
              {["RETRY", "SEND_RECOVERY_REMINDER", "SEND_RECOVERY_LINK", "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"].map(
                (a) => (
                  <option key={a} value={a}>
                    {humanize(a)}
                  </option>
                )
              )}
            </select>
          </div>

          {error && <div className="animate-message-in text-[13px] text-[var(--danger-text)]">{error}</div>}
          {result && <div className="animate-message-in text-[13px] text-[var(--success-text)]">{result}</div>}

          <div className="flex gap-2">
            <button
              disabled={submitting}
              onClick={() => decide("APPROVE")}
              className="rounded-control border border-[var(--border-strong)] px-3 py-2 text-[14px] text-[var(--text-primary)] disabled:opacity-50"
            >
              Approve
            </button>
            <button
              disabled={submitting}
              onClick={() => decide("OVERRIDE")}
              className="rounded-control bg-[var(--accent)] px-3 py-2 text-[14px] text-[var(--on-accent)] disabled:opacity-50"
            >
              Override
            </button>
            <button
              disabled={submitting}
              onClick={() => decide("REJECT")}
              className="rounded-control bg-[var(--danger)] px-3 py-2 text-[14px] text-white disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        </>
      ) : (
        <p className="text-[13px] text-[var(--text-secondary)]">
          You're signed in as viewer — reviewing an escalation (approve, reject, or override)
          requires the reviewer role.
        </p>
      )}
    </div>
  );
}

export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<EscalationSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    setEscalations(null);
    api
      .listEscalations()
      .then((r) => setEscalations(r.escalations))
      .catch((e) => setError(String(e)));
  }, [reloadToken]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-medium">Escalation queue</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          {escalations?.length ?? "…"} case(s) awaiting human review
        </p>
      </div>

      {error && <div className="text-[14px] text-[var(--danger-text)]">Failed to load: {error}</div>}

      <div className="grid grid-cols-[1fr_1.2fr] gap-6">
        <div className="overflow-x-auto rounded-card border border-[var(--border)] bg-[var(--surface-2)]">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[13px] text-[var(--text-secondary)]">
                <th className="px-4 py-3 font-normal">Case</th>
                <th className="px-4 py-3 font-normal">Amount</th>
                <th className="px-4 py-3 font-normal">Proposed action</th>
              </tr>
            </thead>
            <tbody>
              {escalations === null && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-[var(--text-muted)]">
                    Loading…
                  </td>
                </tr>
              )}
              {escalations?.length === 0 && (
                <tr>
                  <td colSpan={3}>
                    <EmptyState
                      icon={IconInbox}
                      heading="Nothing escalated right now"
                      subtext="Cases land here when policy or verification flags them for human review."
                      action={{ label: "Refresh", onClick: () => setReloadToken((t) => t + 1) }}
                    />
                  </td>
                </tr>
              )}
              {escalations?.map((e) => (
                <tr
                  key={e.case_id}
                  onClick={() => setSelected(e.case_id)}
                  className="cursor-pointer border-b border-[var(--border)] last:border-0"
                  style={{ backgroundColor: selected === e.case_id ? "var(--accent-muted)" : undefined }}
                >
                  <td className="px-4 py-3">
                    <div>{e.case_id.slice(0, 8)}…</div>
                    <div className="text-[12px] text-[var(--text-muted)]">{e.merchant_id}</div>
                  </td>
                  <td className="tabular-nums px-4 py-3">
                    {e.currency} {e.amount}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={e.proposed_action ?? "—"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          {selected ? (
            <ReviewPanel key={selected} caseId={selected} onReviewed={() => setReloadToken((t) => t + 1)} />
          ) : (
            <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-6 text-[14px] text-[var(--text-muted)]">
              Select a case to review it.
            </div>
          )}
        </div>
      </div>

      <Link href="/cases" className="text-[13px] text-[var(--accent)]">
        Back to case list →
      </Link>
    </div>
  );
}
