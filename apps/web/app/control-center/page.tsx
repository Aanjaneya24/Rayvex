"use client";

import { useEffect, useState } from "react";
import { api, getStoredRole, SimulatorPreviewResponse } from "@/lib/api";

interface PolicyConfig {
  version: number;
  merchant_id: string | null;
  max_retry_count: number;
  cooldown_seconds: number;
  max_automated_recovery_amount: string;
  max_daily_attempts_per_customer: number;
  prohibited_retry_failure_codes: string[];
  suspicious_velocity_threshold: number;
  suspicious_velocity_window_seconds: number;
  high_value_threshold: string;
  allowed_actions_by_failure_code: Record<string, string[]>;
  allowed_communication_hours_start: number;
  allowed_communication_hours_end: number;
  max_interventions_per_case: number;
  risk_score_threshold: number;
}

const FIELD_GROUPS: { title: string; fields: { key: keyof PolicyConfig; label: string; type: "number" }[] }[] = [
  {
    title: "Retry limits",
    fields: [
      { key: "max_retry_count", label: "Maximum retry count", type: "number" },
      { key: "cooldown_seconds", label: "Cooldown between retries (seconds)", type: "number" },
      { key: "max_interventions_per_case", label: "Maximum interventions per case", type: "number" },
    ],
  },
  {
    title: "Amount thresholds",
    fields: [
      { key: "max_automated_recovery_amount", label: "Maximum automated recovery amount", type: "number" },
      { key: "high_value_threshold", label: "High-value threshold (requires escalation)", type: "number" },
    ],
  },
  {
    title: "Rate limits",
    fields: [
      { key: "max_daily_attempts_per_customer", label: "Maximum daily attempts per customer", type: "number" },
      { key: "suspicious_velocity_threshold", label: "Suspicious velocity threshold (attempts)", type: "number" },
      { key: "suspicious_velocity_window_seconds", label: "Suspicious velocity window (seconds)", type: "number" },
    ],
  },
  {
    title: "Communication & risk",
    fields: [
      { key: "allowed_communication_hours_start", label: "Allowed communication hours — start", type: "number" },
      { key: "allowed_communication_hours_end", label: "Allowed communication hours — end", type: "number" },
      { key: "risk_score_threshold", label: "Risk score threshold (0-1)", type: "number" },
    ],
  },
];

function PromoteUserPanel() {
  const [visible, setVisible] = useState(false);
  const [username, setUsername] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setVisible(getStoredRole() === "reviewer");
  }, []);

  if (!visible) return null;

  const promote = async () => {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.promote(username);
      setResult(`${res.username} is now a reviewer.`);
      setUsername("");
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
      <h2 className="mb-1 text-[16px] font-medium">Promote a user to reviewer</h2>
      <p className="mb-3 text-[13px] text-[var(--text-secondary)]">
        New accounts start as viewer-only. Only an existing reviewer can grant another
        user the ability to act on escalations.
      </p>
      <div className="flex items-center gap-2">
        <input
          className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-1.5 text-[14px]"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <button
          onClick={promote}
          disabled={!username || submitting}
          className="rounded-control bg-[var(--accent)] px-3 py-1.5 text-[14px] text-[var(--on-accent)] disabled:opacity-50"
        >
          {submitting ? "Promoting…" : "Promote"}
        </button>
      </div>
      {result && <p className="mt-2 text-[13px] text-[var(--success-text)]">{result}</p>}
      {error && <p className="mt-2 text-[13px] text-[var(--danger-text)]">{error}</p>}
    </div>
  );
}

function SimulatorPreviewPanel({
  result,
  error,
}: {
  result: SimulatorPreviewResponse | null;
  error: string | null;
}) {

  if (error) {
    return <div className="text-[14px] text-[var(--danger-text)]">Preview failed: {error}</div>;
  }
  if (!result) return null;

  const baseline = result.baseline.intelligent_recovery;
  const draft = result.draft.intelligent_recovery;
  const delta = draft.verified_recovered_revenue - baseline.verified_recovered_revenue;

  return (
    <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
      <h2 className="mb-1 text-[16px] font-medium">Simulated effect (not saved)</h2>
      <p className="mb-3 text-[13px] text-[var(--text-secondary)]">
        {result.case_count}-case simulation, seed {result.seed} · changed: {result.changed_fields.join(", ")}
      </p>
      <div className="grid grid-cols-3 gap-4 text-[14px]">
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Baseline recovered revenue</div>
          <div className="tabular-nums text-[18px]">Rs {baseline.verified_recovered_revenue.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Draft recovered revenue</div>
          <div className="tabular-nums text-[18px]">Rs {draft.verified_recovered_revenue.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Delta</div>
          <div
            className="tabular-nums text-[18px]"
            style={{ color: delta >= 0 ? "var(--success-text)" : "var(--danger-text)" }}
          >
            {delta >= 0 ? "+" : ""}Rs {delta.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Baseline actions taken</div>
          <div className="tabular-nums">{baseline.total_actions_taken}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Draft actions taken</div>
          <div className="tabular-nums">{draft.total_actions_taken}</div>
        </div>
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">Recovery rate (baseline → draft)</div>
          <div className="tabular-nums">
            {(baseline.recovery_rate * 100).toFixed(1)}% → {(draft.recovery_rate * 100).toFixed(1)}%
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ControlCenterPage() {
  const [config, setConfig] = useState<PolicyConfig | null>(null);
  const [draft, setDraft] = useState<PolicyConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedField, setSavedField] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [previewResult, setPreviewResult] = useState<SimulatorPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPolicyConfig<PolicyConfig>()
      .then((data) => {
        setConfig(data);
        setDraft(data);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const handleSave = async (field: keyof PolicyConfig) => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const body = { ...draft, updated_by: "merchant_control_center" };
      const updated = await api.updatePolicyConfig<PolicyConfig>(body);
      setConfig(updated);
      setDraft(updated);
      setSavedField(field);
      setTimeout(() => setSavedField(null), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async (field: keyof PolicyConfig) => {
    if (!draft) return;
    setPreviewing(field);
    setPreviewError(null);
    setPreviewResult(null);
    try {
      const result = await api.previewPolicyChange({
        case_count: 100, seed: 42, [field]: draft[field],
      });
      setPreviewResult(result);
    } catch (e) {
      setPreviewError(String(e));
    } finally {
      setPreviewing(null);
    }
  };

  if (error && !config) {
    return <div className="text-[14px] text-[var(--danger-text)]">Failed to load: {error}</div>;
  }
  if (draft === null) {
    return <div className="h-40 w-full animate-pulse rounded-card bg-[var(--surface-1)]" />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[22px] font-medium">Control center</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          Policy version {config?.version} · merchant: {config?.merchant_id ?? "global default"}
        </p>
        <p className="mt-2 text-[13px] text-[var(--warning-text)]">
          Changes apply to new decisions only — past cases are not retroactively altered.
        </p>
      </div>

      {error && <div className="text-[14px] text-[var(--danger-text)]">Save failed: {error}</div>}

      <PromoteUserPanel />

      <div className="flex flex-col gap-6">
        {FIELD_GROUPS.map((group) => (
          <div key={group.title} className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <h2 className="mb-3 text-[16px] font-medium">{group.title}</h2>
            <div className="flex flex-col gap-3">
              {group.fields.map(({ key, label }) => (
                <div key={key} className="flex items-center gap-3">
                  <label className="w-80 text-[13px] text-[var(--text-secondary)]">{label}</label>
                  <input
                    type="number"
                    value={String(draft[key])}
                    onChange={(e) =>
                      setDraft({ ...draft, [key]: e.target.type === "number" ? Number(e.target.value) : e.target.value })
                    }
                    className="tabular-nums w-40 rounded-control border border-[var(--border-strong)] bg-[var(--surface-2)] px-2 py-1 text-[14px]"
                  />
                  <button
                    onClick={() => handleSave(key)}
                    disabled={saving || draft[key] === config?.[key]}
                    className="rounded-control border border-[var(--border-strong)] px-3 py-1 text-[13px] text-[var(--text-secondary)] disabled:opacity-40"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => handlePreview(key)}
                    disabled={previewing !== null || draft[key] === config?.[key]}
                    className="rounded-control border border-[var(--border-strong)] px-3 py-1 text-[13px] text-[var(--text-secondary)] disabled:opacity-40"
                    title="Preview this change's effect on a 100-case simulation before saving"
                  >
                    {previewing === key ? "Simulating…" : "Preview effect"}
                  </button>
                  {savedField === key && (
                    <span className="text-[13px]" style={{ color: "var(--success-text)" }}>
                      Saved — now version {config?.version}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        <SimulatorPreviewPanel result={previewResult} error={previewError} />

        <div className="rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-4">
          <h2 className="mb-2 text-[16px] font-medium">Prohibited retry failure codes</h2>
          <p className="text-[13px] text-[var(--text-secondary)]">
            {draft.prohibited_retry_failure_codes.join(", ") || "none configured"}
          </p>
          <p className="mt-1 text-[12px] text-[var(--text-muted)]">
            Read-only in this view — editing the list itself is not yet wired to the form.
          </p>
        </div>
      </div>
    </div>
  );
}
