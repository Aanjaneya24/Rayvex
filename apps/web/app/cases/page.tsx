"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IconFilterOff } from "@tabler/icons-react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { api, CaseSummary } from "@/lib/api";

const STATUS_OPTIONS = [
  "", "RECEIVED", "SCREENING", "DIAGNOSING", "ELIGIBILITY_CHECK", "DECISION", "ACTION_PENDING",
  "ACTION_EXECUTED", "VERIFICATION_PENDING", "RECOVERED", "FAILED", "ESCALATED", "STOPPED",
];

export default function CaseListPage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [failureCode, setFailureCode] = useState("");
  const [failureCodeOptions, setFailureCodeOptions] = useState<string[]>([]);
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {

    api.getFailureCodes().then((r) => setFailureCodeOptions(r.failure_codes)).catch(() => {});
  }, []);

  useEffect(() => {
    setCases(null);
    api
      .listCases({
        status: status || undefined,
        failure_code: failureCode || undefined,
        amount_min: amountMin || undefined,
        amount_max: amountMax || undefined,
        created_from: createdFrom ? new Date(createdFrom).toISOString() : undefined,
        created_to: createdTo ? new Date(createdTo).toISOString() : undefined,
        limit: 100,
      })
      .then((r) => {
        setCases(r.cases);
        setTotal(r.total);
      })
      .catch((e) => setError(String(e)));
  }, [status, failureCode, amountMin, amountMax, createdFrom, createdTo]);

  const hasActiveFilters = Boolean(status || failureCode || amountMin || amountMax || createdFrom || createdTo);
  const clearFilters = () => {
    setStatus("");
    setFailureCode("");
    setAmountMin("");
    setAmountMax("");
    setCreatedFrom("");
    setCreatedTo("");
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-medium">Cases</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{total} total</p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Status</label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s || "All"}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Failure type</label>
          <select
            value={failureCode}
            onChange={(e) => setFailureCode(e.target.value)}
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          >
            <option value="">All</option>
            {failureCodeOptions.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Amount min</label>
          <input
            type="number"
            value={amountMin}
            onChange={(e) => setAmountMin(e.target.value)}
            placeholder="0"
            className="tabular-nums w-28 rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Amount max</label>
          <input
            type="number"
            value={amountMax}
            onChange={(e) => setAmountMax(e.target.value)}
            placeholder="Any"
            className="tabular-nums w-28 rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Created from</label>
          <input
            type="date"
            value={createdFrom}
            onChange={(e) => setCreatedFrom(e.target.value)}
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[13px] text-[var(--text-secondary)]">Created to</label>
          <input
            type="date"
            value={createdTo}
            onChange={(e) => setCreatedTo(e.target.value)}
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
          />
        </div>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="rounded-control border border-[var(--border-strong)] px-3 py-1 text-[13px] text-[var(--text-secondary)]"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && <div className="text-[14px] text-[var(--danger-text)]">Failed to load: {error}</div>}

      <div className="overflow-x-auto rounded-card border border-[var(--border)] bg-[var(--surface-2)]">
        <table className="w-full text-[14px]">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-[13px] text-[var(--text-secondary)]">
              <th className="px-4 py-3 font-normal">Case ID</th>
              <th className="px-4 py-3 font-normal">Amount</th>
              <th className="px-4 py-3 font-normal">Failure type</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Recovery confidence</th>
              <th className="px-4 py-3 font-normal">Last updated</th>
            </tr>
          </thead>
          <tbody>
            {cases === null && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-[var(--text-muted)]">
                  Loading…
                </td>
              </tr>
            )}
            {cases?.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={IconFilterOff}
                    heading="No cases match this filter"
                    subtext={hasActiveFilters ? "Try widening the status, failure type, amount, or date range." : undefined}
                    action={hasActiveFilters ? { label: "Clear filters", onClick: clearFilters } : undefined}
                  />
                </td>
              </tr>
            )}
            {cases?.map((c) => (
              <tr key={c.case_id} className="border-b border-[var(--border)] last:border-0">
                <td className="px-4 py-3">
                  <Link href={`/cases/${c.case_id}`} className="text-[var(--accent)]">
                    {c.case_id}
                  </Link>
                </td>
                <td className="tabular-nums px-4 py-3">
                  {c.currency} {c.amount}
                </td>
                <td className="px-4 py-3">{c.failure_code ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={c.status} />
                </td>
                <td className="tabular-nums px-4 py-3">
                  {c.recovery_confidence !== null ? `${(c.recovery_confidence * 100).toFixed(0)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-[var(--text-muted)]">
                  {new Date(c.updated_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
