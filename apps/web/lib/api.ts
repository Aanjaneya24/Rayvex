const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type Credentials = { username: string; password: string };
let currentCredentials: Credentials | null = null;

export function setCredentials(credentials: Credentials | null) {
  currentCredentials = credentials;
  if (typeof window === "undefined") return;
  if (credentials) sessionStorage.setItem("rayvex_dashboard_credentials", JSON.stringify(credentials));
  else sessionStorage.removeItem("rayvex_dashboard_credentials");
}

export function loadStoredCredentials(): Credentials | null {
  if (typeof window === "undefined") return null;
  const stored = sessionStorage.getItem("rayvex_dashboard_credentials");
  if (!stored) return null;
  currentCredentials = JSON.parse(stored);
  return currentCredentials;
}

export function setStoredRole(role: string | null) {
  if (typeof window === "undefined") return;
  if (role) sessionStorage.setItem("rayvex_dashboard_role", role);
  else sessionStorage.removeItem("rayvex_dashboard_role");
}

export function getStoredRole(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("rayvex_dashboard_role");
}

function authHeader(): Record<string, string> {
  if (!currentCredentials) return {};
  const token = btoa(`${currentCredentials.username}:${currentCredentials.password}`);
  return { Authorization: `Basic ${token}` };
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} -> ${response.status}: ${detail}`);
  }
  return response.json();
}

export interface MetricsSummary {
  revenue_at_risk: string;
  verified_recovered_revenue: string;
  recovery_rate: number;
  incremental_revenue_vs_baseline: string | null;
  cases_processed: number;
  cases_recovered: number;
  escalation_rate: number;
  average_recovery_time_seconds: number | null;
  latest_benchmark_run_id: string | null;

  revenue_at_risk_trend_pct: number | null;
  verified_recovered_revenue_trend_pct: number | null;
  recovery_rate_trend_pct: number | null;
}

export interface CaseSummary {
  case_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  failure_code: string | null;
  case_type: string;
  status: string;
  recovery_confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface CaseListResponse {
  total: number;
  limit: number;
  offset: number;
  cases: CaseSummary[];
}

export interface TimelineStep {
  from_state: string | null;
  to_state: string;
  reason: string;
  actor: string;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface AgentTraceEntry {
  proposed_action: string;
  reason: string;
  confidence: number;
  expected_recovery_value: number;
  risk_level: string;
  model_backend: string;
  model_name: string;
  prompt_version: string;
  schema_version: string;
  tool_trace: unknown[];
  created_at: string;

  llm_call_count: number;
  total_latency_ms: number;
  estimated_cost_usd: number;
}

export interface PolicyCheckEntry {
  proposed_action: string;
  verdict_type: string;
  resulting_action: string | null;
  rule_id: string;
  reason: string;
  requires_escalation: boolean;
  policy_config_version: number;
  context_snapshot: Record<string, unknown>;
  created_at: string;
}

export interface VerificationProofEntry {
  mode: "RAZORPAY_TEST_MODE" | "SIMULATION_MODE";
  provider_status: string | null;
  outcome: string;
  raw_response: Record<string, unknown>;
  created_at: string;
}

export interface AlternativeConsidered {
  action: string;
  probability: number;
  source_tier: string;
  expected_recovery_value: number;
  action_cost: number;
  chosen: boolean;
}

export interface CaseDetail {
  case: CaseSummary;
  alternatives_considered: AlternativeConsidered[];
  timeline: TimelineStep[];
  agent_trace: AgentTraceEntry[];
  policy_checks: PolicyCheckEntry[];
  verification_proof: VerificationProofEntry[];
}

export interface BenchmarkStrategyMetrics {
  revenue_at_risk: number;
  verified_recovered_revenue: number;
  recovery_rate: number;
  cases_recovered: number;
  cases_failed: number;
  cases_stopped: number;
  escalations: number;
  total_actions_taken: number;
  total_action_cost: number;
  average_time_to_recovery_seconds: number | null;
  recovery_efficiency: number;
}

export interface BenchmarkRun {
  id: string;
  seed: number;
  case_count: number;
  naive_retry: BenchmarkStrategyMetrics;
  intelligent_recovery: BenchmarkStrategyMetrics;
  unnecessary_actions_avoided: number;
  incremental_verified_revenue: string;
  created_at: string;
}

export interface EscalationSummary {
  case_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  failure_code: string | null;
  proposed_action: string | null;
  confidence: number | null;
  escalated_at: string;
}

export interface EscalationListResponse {
  total: number;
  escalations: EscalationSummary[];
}

export interface EscalationAgentTraceEntry {
  proposed_action: string;
  reason: string;
  confidence: number;
  risk_level: string;
  model_backend: string;
  created_at: string;
}

export interface PriorReview {
  reviewer: string;
  decision: string;
  original_proposed_action: string | null;
  final_action: string | null;
  reason: string;
  created_at: string;
}

export interface EscalationDetail {
  case_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  failure_code: string | null;
  payment_method: string | null;
  timeline: TimelineStep[];
  agent_trace: EscalationAgentTraceEntry[];
  prior_reviews: PriorReview[];
}

export interface ReviewResponse {
  review_id: string;
  decision: string;
  final_action: string | null;
  gate_approved: boolean | null;
  verification_outcome: string | null;
}

export interface ObservabilitySummary {
  total_decisions: number;
  deterministic_skips: number;
  deterministic_skip_rate: number;
  total_llm_calls: number;
  total_latency_ms: number;
  total_estimated_cost_usd: number;
  average_latency_ms_per_live_decision: number | null;
  average_llm_calls_per_live_decision: number | null;
}

export interface SimulatorStrategyMetrics {
  revenue_at_risk: number;
  verified_recovered_revenue: number;
  recovery_rate: number;
  total_actions_taken: number;
  total_action_cost: number;
  recovery_efficiency: number;
}

export interface SimulatorPreviewResponse {
  case_count: number;
  seed: number;
  changed_fields: string[];
  current_config_version: number;
  baseline: { naive_retry: SimulatorStrategyMetrics; intelligent_recovery: SimulatorStrategyMetrics; incremental_verified_revenue: string };
  draft: { naive_retry: SimulatorStrategyMetrics; intelligent_recovery: SimulatorStrategyMetrics; incremental_verified_revenue: string };
}

export interface AuthMeResponse {
  username: string;
  role: string;
}

export const api = {
  register: (username: string, password: string) =>
    fetchJson<{ username: string; role: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => fetchJson<AuthMeResponse>("/auth/me"),
  promote: (username: string) =>
    fetchJson<{ username: string; role: string }>("/auth/promote", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),
  getMetricsSummary: () => fetchJson<MetricsSummary>("/metrics/summary"),
  getPolicyConfig: <T = Record<string, unknown>>() => fetchJson<T>("/policy/config"),
  updatePolicyConfig: <T = Record<string, unknown>>(body: Record<string, unknown>) =>
    fetchJson<T>("/policy/config", { method: "PUT", body: JSON.stringify(body) }),
  previewPolicyChange: (body: Record<string, unknown>) =>
    fetchJson<SimulatorPreviewResponse>("/simulator/preview", { method: "POST", body: JSON.stringify(body) }),
  listCases: (params?: {
    status?: string;
    failure_code?: string;
    amount_min?: string;
    amount_max?: string;
    created_from?: string;
    created_to?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.failure_code) qs.set("failure_code", params.failure_code);
    if (params?.amount_min) qs.set("amount_min", params.amount_min);
    if (params?.amount_max) qs.set("amount_max", params.amount_max);
    if (params?.created_from) qs.set("created_from", params.created_from);
    if (params?.created_to) qs.set("created_to", params.created_to);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return fetchJson<CaseListResponse>(`/cases${suffix}`);
  },
  getCaseDetail: (caseId: string) => fetchJson<CaseDetail>(`/cases/${caseId}`),
  runBenchmark: (caseCount: number, seed = 42, runToken?: string) =>
    fetchJson<BenchmarkRun>("/evaluation/benchmark", {
      method: "POST",
      body: JSON.stringify({ case_count: caseCount, seed, run_token: runToken }),
    }),
  getBenchmarkProgress: (runToken: string) =>
    fetchJson<{ phase: string | null; processed: number | null; total: number | null }>(
      `/evaluation/benchmark/progress/${runToken}`
    ),
  listBenchmarkRuns: () => fetchJson<{ runs: BenchmarkRun[] }>("/evaluation/benchmark"),
  getBenchmarkRun: (runId: string) => fetchJson<BenchmarkRun>(`/evaluation/benchmark/${runId}`),
  getObservabilitySummary: () => fetchJson<ObservabilitySummary>("/observability/summary"),
  getFailureCodes: () => fetchJson<{ failure_codes: string[] }>("/cases/failure-codes"),
  listEscalations: () => fetchJson<EscalationListResponse>("/escalations"),
  getEscalationDetail: (caseId: string) => fetchJson<EscalationDetail>(`/escalations/${caseId}`),
  reviewEscalation: (
    caseId: string,
    body: { decision: "APPROVE" | "REJECT" | "OVERRIDE"; reason: string; action?: string },
  ) =>
    fetchJson<ReviewResponse>(`/escalations/${caseId}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
