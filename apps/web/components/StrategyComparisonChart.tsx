"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BenchmarkStrategyMetrics } from "@/lib/api";

interface StrategyComparisonChartProps {
  naive: BenchmarkStrategyMetrics;
  intelligent: BenchmarkStrategyMetrics;
}

// Revenue and recovery rate use different units, so they're two small
// grouped-bar panels rather than one chart with two incompatible axes.
export function StrategyComparisonChart({ naive, intelligent }: StrategyComparisonChartProps) {
  const revenueData = [
    {
      metric: "Revenue at risk",
      "Naive retry": naive.revenue_at_risk,
      "Rayvex": intelligent.revenue_at_risk,
    },
    {
      metric: "Verified recovered",
      "Naive retry": naive.verified_recovered_revenue,
      "Rayvex": intelligent.verified_recovered_revenue,
    },
  ];
  const rateData = [
    {
      metric: "Recovery rate",
      "Naive retry": Number((naive.recovery_rate * 100).toFixed(1)),
      "Rayvex": Number((intelligent.recovery_rate * 100).toFixed(1)),
    },
  ];

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={revenueData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={6}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="metric"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              tickFormatter={(v: number) => `Rs ${v.toLocaleString("en-IN")}`}
              width={90}
            />
            <Tooltip
              formatter={(value) => `Rs ${Number(value ?? 0).toLocaleString("en-IN")}`}
              contentStyle={{
                background: "var(--surface-2)",
                border: "1px solid var(--border-strong)",
                borderRadius: 8,
                fontSize: 13,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 13, color: "var(--text-secondary)" }} />
            <Bar dataKey="Naive retry" fill="var(--neutral-tag)" radius={4} isAnimationActive animationDuration={500} />
            <Bar dataKey="Rayvex" fill="var(--accent)" radius={4} isAnimationActive animationDuration={500} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rateData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={6}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="metric"
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
            />
            <YAxis
              domain={[0, 100]}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
              tickFormatter={(v: number) => `${v}%`}
              width={40}
            />
            <Tooltip
              formatter={(value) => `${value}%`}
              contentStyle={{
                background: "var(--surface-2)",
                border: "1px solid var(--border-strong)",
                borderRadius: 8,
                fontSize: 13,
              }}
            />
            <Bar dataKey="Naive retry" fill="var(--neutral-tag)" radius={4} isAnimationActive animationDuration={500} />
            <Bar dataKey="Rayvex" fill="var(--accent)" radius={4} isAnimationActive animationDuration={500} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
