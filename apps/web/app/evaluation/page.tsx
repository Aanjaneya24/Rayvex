"use client";

import { useState } from "react";
import { MetricCard } from "@/components/MetricCard";
import { ScrollReveal } from "@/components/ScrollReveal";
import { StrategyComparisonChart } from "@/components/StrategyComparisonChart";
import { useCountUp } from "@/hooks/useCountUp";
import { api, BenchmarkRun } from "@/lib/api";

const CASE_COUNT_OPTIONS = [100, 500, 1000, 5000, 10000];

interface ProgressState {
  phase: string | null;
  processed: number | null;
  total: number | null;
}

export default function EvaluationPage() {
  const [caseCount, setCaseCount] = useState(500);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<BenchmarkRun | null>(null);
  const [progress, setProgress] = useState<ProgressState | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setRun(null);
    setProgress(null);

    const runToken = crypto.randomUUID();
    const pollInterval = setInterval(() => {
      api
        .getBenchmarkProgress(runToken)
        .then((p) => {
          if (p.processed !== null) setProgress(p);
        })
        .catch(() => {});
    }, 400);

    try {
      const result = await api.runBenchmark(caseCount, 42, runToken);
      setRun(result);
    } catch (e) {
      setError(String(e));
    } finally {
      clearInterval(pollInterval);
      setRunning(false);
      setProgress(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-medium">Evaluation</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          Rayvex (intelligent recovery) vs. naive retry, run against the same seeded synthetic
          case population — labeled as a synthetic benchmark, not real-world performance.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-[13px] text-[var(--text-secondary)]">Case count</label>
        <select
          value={caseCount}
          onChange={(e) => setCaseCount(Number(e.target.value))}
          disabled={running}
          className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
        >
          {CASE_COUNT_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n.toLocaleString("en-IN")}
            </option>
          ))}
        </select>
        <button
          onClick={handleRun}
          disabled={running}
          className="rounded-control bg-[var(--accent)] px-4 py-1.5 text-[14px] text-[var(--on-accent)] disabled:opacity-60"
        >
          {running ? "Running…" : "Run benchmark"}
        </button>
      </div>

      {error && <div className="text-[14px] text-[var(--danger-text)]">Run failed: {error}</div>}

      {running && (
        <div className="flex flex-col gap-2">
          <div className="text-[13px] text-[var(--text-muted)]">
            {progress?.processed != null && progress.total != null ? (
              <>
                {progress.phase === "naive" ? "Naive retry pass" : "Rayvex (intelligent) pass"} —{" "}
                <span className="tabular-nums">
                  {progress.processed.toLocaleString("en-IN")} / {progress.total.toLocaleString("en-IN")}
                </span>{" "}
                cases processed
              </>
            ) : (
              <>
                Starting {caseCount.toLocaleString("en-IN")} cases through both strategies — real
                probability/policy queries per case, this can take a while for larger counts.
              </>
            )}
          </div>
          {progress?.processed != null && progress.total != null && (
            <div className="h-1.5 w-full max-w-md overflow-hidden rounded-full bg-[var(--surface-1)]">
              <div
                className="h-1.5 rounded-full bg-[var(--accent)] transition-[width] duration-300 ease-out"
                style={{
                  width: `${
                    ((progress.phase === "intelligent" ? progress.total + progress.processed : progress.processed) /
                      (progress.total * 2)) *
                    100
                  }%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      {run && (
        <ScrollReveal>
          <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <StrategyComparisonChart naive={run.naive_retry} intelligent={run.intelligent_recovery} />
          </div>
        </ScrollReveal>
      )}

      {run && (
        <ScrollReveal delayMs={80}>
          <div className="grid grid-cols-2 gap-6">
            <StrategyPanel title="Naive retry" metrics={run.naive_retry} highlight={false} />
            <StrategyPanel title="Rayvex (intelligent recovery)" metrics={run.intelligent_recovery} highlight />
          </div>
        </ScrollReveal>
      )}

      {run && (
        <div className="grid grid-cols-3 gap-4">
          <MetricCard
            label="Incremental verified revenue"
            value={Number(run.incremental_verified_revenue)}
            prefix="Rs "
          />
          <MetricCard label="Unnecessary actions avoided" value={run.unnecessary_actions_avoided} />
          <MetricCard label="Cases evaluated" value={run.case_count} />
        </div>
      )}
    </div>
  );
}

function CountUpCell({ target, decimals = 0, format }: { target: number; decimals?: number; format: (n: number) => string }) {
  const scale = 10 ** decimals;
  const animated = useCountUp(Math.round(target * scale));
  return <>{format(animated / scale)}</>;
}

function StrategyPanel({
  title,
  metrics,
  highlight,
}: {
  title: string;
  metrics: BenchmarkRun["naive_retry"];
  highlight: boolean;
}) {
  const rows: { label: string; render: React.ReactNode }[] = [
    {
      label: "Revenue at risk",
      render: <CountUpCell target={metrics.revenue_at_risk} format={(n) => `Rs ${n.toLocaleString("en-IN")}`} />,
    },
    {
      label: "Verified recovered revenue",
      render: (
        <CountUpCell target={metrics.verified_recovered_revenue} format={(n) => `Rs ${n.toLocaleString("en-IN")}`} />
      ),
    },
    {
      label: "Recovery rate",
      render: <CountUpCell target={metrics.recovery_rate * 100} decimals={1} format={(n) => `${n.toFixed(1)}%`} />,
    },
    {
      label: "Actions taken",
      render: <CountUpCell target={metrics.total_actions_taken} format={(n) => n.toLocaleString("en-IN")} />,
    },
    {
      label: "Escalations",
      render: <CountUpCell target={metrics.escalations} format={(n) => n.toLocaleString("en-IN")} />,
    },
    {
      label: "Avg. time to recovery",
      render:
        metrics.average_time_to_recovery_seconds !== null ? (
          <CountUpCell target={metrics.average_time_to_recovery_seconds} format={(n) => `${Math.round(n)}s`} />
        ) : (
          "n/a"
        ),
    },
    {
      label: "Recovery efficiency",
      render: (
        <CountUpCell
          target={metrics.recovery_efficiency}
          decimals={2}
          format={(n) => `Rs ${n.toFixed(2)} / action`}
        />
      ),
    },
  ];
  return (
    <div
      className="rounded-card border border-[var(--border)] p-4"
      style={{ backgroundColor: highlight ? "var(--accent-muted)" : "var(--surface-2)" }}
    >
      <h3 className="mb-3 text-[16px] font-medium">{title}</h3>
      <table className="w-full text-[14px]">
        <tbody>
          {rows.map(({ label, render }) => (
            <tr key={label} className="border-b border-[var(--border)] last:border-0">
              <td className="py-2 text-[var(--text-secondary)]">{label}</td>
              <td className="tabular-nums py-2 text-right font-medium">{render}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
