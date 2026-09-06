"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { IconMessageOff, IconReceiptOff, IconShieldOff } from "@tabler/icons-react";
import { EmptyState } from "@/components/EmptyState";
import { ScrollReveal } from "@/components/ScrollReveal";
import { TiltCard } from "@/components/TiltCard";
import { ProviderModeBadge, StatusBadge } from "@/components/StatusBadge";
import { failureTypeLabel, humanize } from "@/lib/labels";
import { reportProviderMode } from "@/lib/providerMode";
import { api, CaseDetail } from "@/lib/api";

const LIVE_POLL_INTERVAL_MS = 5000;

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"agent" | "policy" | "audit">("agent");
  const [justChanged, setJustChanged] = useState(false);
  const previousStatus = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .getCaseDetail(params.id)
        .then((fresh) => {
          if (cancelled) return;
          if (previousStatus.current !== null && previousStatus.current !== fresh.case.status) {
            setJustChanged(true);
            setTimeout(() => setJustChanged(false), 900);
          }
          previousStatus.current = fresh.case.status;
          setDetail(fresh);
        })
        .catch((e) => !cancelled && setError(String(e)));
    };
    load();
    const interval = setInterval(load, LIVE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [params.id]);

  // The top bar's mode pill mirrors this same per-case verification data —
  // reported here, cleared on unmount so it never shows a stale mode on a
  // page that isn't a case detail page.
  useEffect(() => {
    const latest = detail?.verification_proof[detail.verification_proof.length - 1] ?? null;
    reportProviderMode(latest?.mode ?? null);
    return () => reportProviderMode(null);
  }, [detail]);

  if (error) {
    return <div className="text-[14px] text-[var(--danger-text)]">Failed to load: {error}</div>;
  }
  if (detail === null) {
    return <div className="h-40 w-full animate-pulse rounded-card bg-[var(--surface-1)]" />;
  }

  const latestDecision = detail.agent_trace[detail.agent_trace.length - 1] ?? null;
  const latestVerification = detail.verification_proof[detail.verification_proof.length - 1] ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div
        className="flex items-center gap-3 rounded-control transition-colors duration-300"
        style={{ backgroundColor: justChanged ? "var(--accent-muted)" : "transparent" }}
      >
        <h1 className="text-[22px] font-medium">{detail.case.case_id}</h1>
        <StatusBadge status={detail.case.status} />
        {latestVerification && <ProviderModeBadge mode={latestVerification.mode} />}
      </div>
      <div className="text-[14px] text-[var(--text-secondary)]">
        {detail.case.currency} {detail.case.amount} ·{" "}
        {detail.case.failure_code ? failureTypeLabel(detail.case.failure_code) : "no failure code"} ·{" "}
        {humanize(detail.case.case_type)}
      </div>

      <div className="grid grid-cols-[280px_1fr_320px] gap-6">
        <div className="flex flex-col gap-4">
          <WhyPanel
            label="Recovery confidence"
            value={latestDecision ? `${(latestDecision.confidence * 100).toFixed(0)}%` : "—"}
            reason={latestDecision?.reason ?? "No agent decision recorded yet for this case."}
          />
          <WhyPanel
            label="Risk level"
            value={humanize(latestDecision?.risk_level)}
            reason={
              latestDecision
                ? `Assessed at decision time (${latestDecision.model_backend}).`
                : "Not yet assessed."
            }
          />
          <WhyPanel
            label="Expected recovery value"
            value={
              latestDecision
                ? `Rs ${latestDecision.expected_recovery_value.toLocaleString("en-IN")}`
                : "—"
            }
            reason="P(success) x amount - action cost - risk cost."
          />
        </div>

        <div>
          <h2 className="mb-3 text-[18px] font-medium">Timeline</h2>
          <ol className="flex flex-col gap-4 border-l border-[var(--border)] pl-4">
            {detail.timeline.map((step, i) => (
              <li key={i}>
                <ScrollReveal delayMs={i * 40}>
                  <div className="text-[14px] font-medium">
                    {step.from_state ? `${humanize(step.from_state)} -> ` : ""}
                    {humanize(step.to_state)}
                  </div>
                  <div className="text-[13px] text-[var(--text-secondary)]">{step.reason}</div>
                  <div className="text-[12px] text-[var(--text-muted)]">
                    {step.actor} · {new Date(step.created_at).toLocaleString()}
                  </div>
                </ScrollReveal>
              </li>
            ))}
          </ol>
        </div>

        <div>
          <div className="mb-3 flex gap-1 border-b border-[var(--border)]">
            {(["agent", "policy", "audit"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-3 py-2 text-[13px] capitalize"
                style={{
                  color: tab === t ? "var(--accent)" : "var(--text-secondary)",
                  borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
                }}
              >
                {t === "agent" ? "Agent trace" : t === "policy" ? "Policy checks" : "Audit trail"}
              </button>
            ))}
          </div>

          {tab === "agent" && (
            <div className="flex flex-col gap-3">
              {detail.agent_trace.length === 0 && (
                <EmptyState icon={IconMessageOff} heading="No agent decisions yet" />
              )}
              {detail.agent_trace.map((d, i) => (
                <TiltCard key={i}>
                  <div className="text-[14px] font-medium">{humanize(d.proposed_action)}</div>
                  <div className="text-[13px] text-[var(--text-secondary)]">{d.reason}</div>
                  <div className="mt-1 text-[12px] text-[var(--text-muted)]">
                    {d.model_backend} ({d.model_name}) · prompt v{d.prompt_version} · schema v
                    {d.schema_version}
                  </div>
                  <div className="mt-1 text-[12px] text-[var(--text-muted)]">
                    {d.llm_call_count === 0 ? (
                      <span>LLM skipped (deterministic policy), $0.00, 0ms</span>
                    ) : (
                      <span>
                        {d.llm_call_count} LLM call{d.llm_call_count === 1 ? "" : "s"} ·{" "}
                        {d.total_latency_ms}ms · ${d.estimated_cost_usd.toFixed(4)} (estimated)
                      </span>
                    )}
                  </div>
                </TiltCard>
              ))}
            </div>
          )}

          {tab === "policy" && (
            <div className="flex flex-col gap-3">
              {detail.policy_checks.length === 0 && (
                <EmptyState icon={IconShieldOff} heading="No policy checks yet" />
              )}
              {detail.policy_checks.map((p, i) => (
                <TiltCard key={i}>
                  <div className="text-[14px] font-medium">
                    {humanize(p.verdict_type)}
                    {p.resulting_action ? ` -> ${humanize(p.resulting_action)}` : ""}
                  </div>
                  <div className="text-[13px] text-[var(--text-secondary)]">{p.reason}</div>
                  <div className="mt-1 text-[12px] text-[var(--text-muted)]">
                    rule: {p.rule_id} · config v{p.policy_config_version}
                    {p.requires_escalation ? " · requires escalation" : ""}
                  </div>
                </TiltCard>
              ))}
            </div>
          )}

          {tab === "audit" && (
            <div className="flex flex-col gap-3">
              {detail.verification_proof.length > 0 && (
                <p className="text-[12px] text-[var(--text-muted)]">
                  Every verification attempt, including ones that didn&apos;t change the case&apos;s
                  state; that&apos;s why some entries here have no matching Timeline step.
                </p>
              )}
              {detail.verification_proof.length === 0 && (
                <EmptyState icon={IconReceiptOff} heading="No verification attempts yet" />
              )}
              {detail.verification_proof.map((v, i) => {
                const { label, note } = describeVerificationOutcome(v.outcome, v.provider_status);
                return (
                  <TiltCard key={i}>
                    <div className="flex items-center gap-2 text-[14px] font-medium">
                      {label}
                      <ProviderModeBadge mode={v.mode} />
                    </div>
                    <div className="text-[13px] text-[var(--text-secondary)]">{note}</div>
                    <div className="mt-1 text-[12px] text-[var(--text-muted)]">
                      {new Date(v.created_at).toLocaleString()}
                    </div>
                  </TiltCard>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <section>
        <h2 className="mb-2 text-[18px] font-medium">Why this action? / why not the alternatives?</h2>
        {latestDecision ? (
          <p className="text-[14px] text-[var(--text-secondary)]">{latestDecision.reason}</p>
        ) : (
          <p className="text-[14px] text-[var(--text-muted)]">No decision has been made for this case yet.</p>
        )}

        {detail.alternatives_considered.length > 0 ? (
          <div className="mt-3 overflow-x-auto rounded-card border border-[var(--border)]">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-[var(--text-secondary)]">
                  <th className="px-3 py-2 font-normal">Action</th>
                  <th className="px-3 py-2 font-normal">Recovery probability</th>
                  <th className="px-3 py-2 font-normal">Source</th>
                  <th className="px-3 py-2 font-normal">Expected value</th>
                </tr>
              </thead>
              <tbody>
                {detail.alternatives_considered.map((a) => (
                  <tr
                    key={a.action}
                    className="border-b border-[var(--border)] last:border-0"
                    style={{ backgroundColor: a.chosen ? "var(--accent-muted)" : undefined }}
                  >
                    <td className="px-3 py-2 font-medium">
                      {humanize(a.action)}
                      {a.chosen && (
                        <span className="ml-2 text-[12px]" style={{ color: "var(--accent)" }}>
                          chosen
                        </span>
                      )}
                    </td>
                    <td className="tabular-nums px-3 py-2">{(a.probability * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{humanize(a.source_tier)}</td>
                    <td className="tabular-nums px-3 py-2">
                      Rs {a.expected_recovery_value.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-[13px] text-[var(--text-muted)]">
            No alternative-action comparison available yet for this case (no failure code/payment
            method recorded).
          </p>
        )}
      </section>
    </div>
  );
}

function describeVerificationOutcome(
  outcome: string,
  providerStatus: string | null
): { label: string; note: string } {
  if (outcome === "ERROR" && providerStatus === null) {
    return {
      label: "No live provider status; verification call failed",
      note: "The provider call itself couldn't be completed (timeout/network error), not a claim about the payment. The case stays exactly where it was; verification will be retried.",
    };
  }
  return { label: humanize(outcome), note: `provider status: ${providerStatus ?? "n/a"}` };
}

function WhyPanel({ label, value, reason }: { label: string; value: string; reason: string }) {
  return (
    <TiltCard>
      <div className="text-[13px] text-[var(--text-secondary)]">{label}</div>
      <div className="tabular-nums mt-1 text-[20px] font-medium">{value}</div>
      <div className="mt-1 text-[12px] text-[var(--text-muted)]">{reason}</div>
    </TiltCard>
  );
}
