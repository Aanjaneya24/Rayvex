// Presentation-only: maps raw snake_case/UPPER_CASE API values to
// human-readable text. Never used for values sent back to the API.

// Explicit map for values the fallback formatter can't capitalize
// correctly (acronyms like OTP, 3D Secure).
const FAILURE_TYPE_LABELS: Record<string, string> = {
  bank_timeout: "Bank timeout",
  gateway_timeout: "Gateway timeout",
  network_error: "Network error",
  otp_failure: "OTP failure",
  "3ds_abandonment": "3D Secure abandonment",
  checkout_abandonment: "Checkout abandonment",
  insufficient_funds: "Insufficient funds",
  card_declined: "Card declined",
  invalid_payment_method: "Invalid payment method",
  gateway_degradation: "Gateway degradation",
  bank_downtime: "Bank downtime",
  suspicious_velocity: "Suspicious velocity",
  repeated_attempts: "Repeated attempts",
  abnormal_amount: "Abnormal amount",
};

function autoFormat(raw: string): string {
  const spaced = raw.toLowerCase().replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function failureTypeLabel(raw: string | null | undefined): string {
  if (!raw) return "—";
  return FAILURE_TYPE_LABELS[raw] ?? autoFormat(raw);
}

// General-purpose humanizer for other snake_case/UPPER_CASE values
// (actions, verdicts, outcomes, risk levels, timeline states).
export function humanize(raw: string | null | undefined): string {
  if (!raw) return "—";
  return autoFormat(raw);
}
