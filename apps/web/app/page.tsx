"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MetricCard } from "@/components/MetricCard";
import { RecoveryFunnelChart } from "@/components/RecoveryFunnelChart";
import { StatusBadge } from "@/components/StatusBadge";
import { StrategyComparisonChart } from "@/components/StrategyComparisonChart";
import { api, BenchmarkRun, CaseSummary, MetricsSummary, ObservabilitySummary } from "@/lib/api";

export default function CommandCenterPage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [observability, setObservability] = useState<ObservabilitySummary | null>(null);
  const [latestBenchmark, setLatestBenchmark] = useState<BenchmarkRun | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getMetricsSummary().then((m) => {
      setMetrics(m);
      if (m.latest_benchmark_run_id) {
        api.getBenchmarkRun(m.latest_benchmark_run_id).then(setLatestBenchmark).catch(() => setLatestBenchmark(null));
      } else {
        setLatestBenchmark(null);
      }
    }).catch((e) => setError(String(e)));
    api.listCases({ limit: 10 }).then((r) => setCases(r.cases)).catch((e) => setError(String(e)));
    api.getObservabilitySummary().then(setObservability).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div className="text-[14px] text-[var(--danger-text)]">Failed to load: {error}</div>;
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-[22px] font-medium">Command center</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          Every number below is computed live from the database — nothing here is illustrative.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Revenue at risk"
          value={metrics ? Number(metrics.revenue_at_risk) : null}
          prefix="Rs "
          trendPct={metrics?.revenue_at_risk_trend_pct}
          trendTone="neutral"
        />
        <MetricCard
          label="Verified recovered revenue"
          value={metrics ? Number(metrics.verified_recovered_revenue) : null}
          prefix="Rs "
          trendPct={metrics?.verified_recovered_revenue_trend_pct}
        />
        <MetricCard
          label="Recovery rate"
          value={metrics ? metrics.recovery_rate * 100 : null}
          decimals={1}
          suffix="%"
          trendPct={metrics?.recovery_rate_trend_pct}
        />
        <MetricCard
          label="Incremental revenue vs. baseline"
          value={
            metrics?.incremental_revenue_vs_baseline !== undefined &&
            metrics?.incremental_revenue_vs_baseline !== null
              ? Number(metrics.incremental_revenue_vs_baseline)
              : metrics
              ? 0
              : null
          }
          prefix="Rs "
        />
      </div>

      <RecoveryFunnel cases={cases} />

      <StrategyComparisonPanel run={latestBenchmark} />

      <ObservabilityPanel observability={observability} />

      <section>
        <h2 className="mb-3 text-[18px] font-medium">Recent cases</h2>
        <div className="overflow-x-auto rounded-card border border-[var(--border)] bg-[var(--surface-2)]">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[13px] text-[var(--text-secondary)]">
                <th className="px-4 py-3 font-normal">Case</th>
                <th className="px-4 py-3 font-normal">Amount</th>
                <th className="px-4 py-3 font-normal">Failure</th>
                <th className="px-4 py-3 font-normal">Status</th>
                <th className="px-4 py-3 font-normal">Updated</th>
              </tr>
            </thead>
            <tbody>
              {cases === null && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-[var(--text-muted)]">
                    Loading…
                  </td>
                </tr>
              )}
              {cases?.map((c) => (

                <tr
                  key={c.case_id}
                  className="cursor-pointer border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-1)]"
                  tabIndex={0}
                  role="link"
                  onClick={() => router.push(`/cases/${c.case_id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") router.push(`/cases/${c.case_id}`);
                  }}
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/cases/${c.case_id}`}
                      className="text-[var(--accent)]"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {c.case_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="tabular-nums px-4 py-3">
                    {c.currency} {c.amount}
                  </td>
                  <td className="px-4 py-3">{c.failure_code ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">
                    {new Date(c.updated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ObservabilityPanel({ observability }: { observability: ObservabilitySummary | null }) {

  if (observability === null) {
    return <div className="h-24 w-full animate-pulse rounded-card bg-[var(--surface-1)]" />;
  }
  return (
    <section>
      <h2 className="mb-3 text-[18px] font-medium">Agent observability</h2>
      <div className="grid grid-cols-4 gap-4 rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4 text-[14px]">
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Decisions</div>
          <div className="tabular-nums text-[18px]">{observability.total_decisions}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">LLM skipped (deterministic)</div>
          <div className="tabular-nums text-[18px]">
            {observability.deterministic_skips} ({(observability.deterministic_skip_rate * 100).toFixed(0)}%)
          </div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Avg latency / live decision</div>
          <div className="tabular-nums text-[18px]">
            {observability.average_latency_ms_per_live_decision !== null
              ? `${observability.average_latency_ms_per_live_decision.toFixed(0)}ms`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Total estimated LLM cost</div>
          <div className="tabular-nums text-[18px]">${observability.total_estimated_cost_usd.toFixed(4)}</div>
        </div>
      </div>
    </section>
  );
}

function RecoveryFunnel({ cases }: { cases: CaseSummary[] | null }) {

  if (cases === null) {
    return <div className="h-24 w-full animate-pulse rounded-card bg-[var(--surface-1)]" />;
  }
  return (
    <section>
      <h2 className="mb-3 text-[18px] font-medium">Recovery funnel</h2>
      <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
        <RecoveryFunnelChart cases={cases} />
      </div>
    </section>
  );
}

function StrategyComparisonPanel({ run }: { run: BenchmarkRun | null | undefined }) {

  return (
    <section>
      <h2 className="mb-3 text-[18px] font-medium">Rayvex vs. naive retry</h2>
      <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
        {run === undefined && <div className="h-[220px] w-full animate-pulse rounded-card bg-[var(--surface-1)]" />}
        {run === null && (
          <div className="flex h-[220px] flex-col items-center justify-center gap-2 text-center">
            <p className="text-[14px] text-[var(--text-secondary)]">
              No batch evaluation has been run yet — this panel has nothing real to show.
            </p>
            <Link href="/evaluation" className="text-[14px] text-[var(--accent)]">
              Run one on the Evaluation page →
            </Link>
          </div>
        )}
        {run && (
          <>
            <p className="mb-2 text-[13px] text-[var(--text-secondary)]">
              Most recent batch run — {run.case_count.toLocaleString("en-IN")} cases, seed {run.seed}
            </p>
            <StrategyComparisonChart naive={run.naive_retry} intelligent={run.intelligent_recovery} />
          </>
        )}
      </div>
    </section>
  );
}
