"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { CaseSummary } from "@/lib/api";

interface FunnelStage {
  label: string;
  count: number;
}

function stagesFrom(cases: CaseSummary[]): FunnelStage[] {
  return [
    { label: "Revenue at risk", count: cases.length },
    { label: "Diagnosed", count: cases.filter((c) => c.status !== "RECEIVED").length },
    {
      label: "Eligible",
      count: cases.filter((c) => !["RECEIVED", "SCREENING", "STOPPED"].includes(c.status)).length,
    },
    {
      label: "Action taken",
      count: cases.filter((c) =>
        ["ACTION_EXECUTED", "VERIFICATION_PENDING", "RECOVERED", "FAILED", "ESCALATED"].includes(c.status)
      ).length,
    },
    { label: "Verified recovered", count: cases.filter((c) => c.status === "RECOVERED").length },
  ];
}

// A horizontal bar chart, growing to its real width on load, without
// pulling in a dedicated funnel chart type Recharts doesn't ship.
export function RecoveryFunnelChart({ cases }: { cases: CaseSummary[] }) {
  const stages = stagesFrom(cases);
  const max = Math.max(1, ...stages.map((s) => s.count));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        layout="vertical"
        data={stages}
        margin={{ top: 4, right: 32, bottom: 4, left: 4 }}
        barCategoryGap={14}
      >
        <XAxis type="number" domain={[0, max]} hide />
        <YAxis
          type="category"
          dataKey="label"
          width={132}
          tickLine={false}
          axisLine={false}
          tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
        />
        <Bar dataKey="count" radius={4} isAnimationActive animationDuration={500}>
          {stages.map((s) => (
            <Cell key={s.label} fill="var(--accent)" />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            style={{ fill: "var(--text-primary)", fontSize: 13, fontVariantNumeric: "tabular-nums" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
