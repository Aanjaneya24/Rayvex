"use client";

import { TiltCard } from "@/components/TiltCard";
import { useCountUp } from "@/hooks/useCountUp";

export function MetricCard({
  label,
  value,
  prefix = "",
  suffix = "",
  decimals = 0,
  trendPct,
  trendTone = "good-bad",
}: {
  label: string;
  value: number | null;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  trendPct?: number | null;

  trendTone?: "good-bad" | "neutral";
}) {
  const scale = 10 ** decimals;
  const animated = useCountUp(value === null ? 0 : Math.round(value * scale));
  return (
    <TiltCard>
      <div className="text-[13px] font-normal text-[var(--text-secondary)]">{label}</div>
      {value === null ? (
        <div className="mt-1 h-[28px] w-24 animate-pulse rounded bg-[var(--surface-1)]" />
      ) : (
        <div className="tabular-nums mt-1 text-[24px] font-medium text-[var(--text-primary)]">
          {prefix}
          {decimals > 0 ? (animated / scale).toFixed(decimals) : animated.toLocaleString("en-IN")}
          {suffix}
        </div>
      )}
      {value !== null && trendPct !== undefined && trendPct !== null && (
        <div
          className="tabular-nums mt-1 text-[13px]"
          style={{
            color:
              trendTone === "neutral"
                ? "var(--accent)"
                : trendPct >= 0
                ? "var(--success-text)"
                : "var(--danger-text)",
          }}
        >
          {trendPct >= 0 ? "▲" : "▼"} {Math.abs(trendPct * 100).toFixed(1)}% vs 24h ago
        </div>
      )}
    </TiltCard>
  );
}
