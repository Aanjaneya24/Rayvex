const IN_PROGRESS_STATES = new Set([
  "SCREENING", "DIAGNOSING", "ELIGIBILITY_CHECK", "DECISION",
  "ACTION_PENDING", "ACTION_EXECUTED", "VERIFICATION_PENDING",
]);

function toneFor(status: string): { bg: string; fg: string } {
  if (status === "RECOVERED") {
    return { bg: "var(--success)", fg: "#FFFFFF" };
  }
  if (status === "FAILED" || status === "STOPPED") {
    return { bg: "var(--danger)", fg: "#FFFFFF" };
  }
  if (status === "ESCALATED" || IN_PROGRESS_STATES.has(status)) {
    return { bg: "var(--warning)", fg: "#FFFFFF" };
  }

  return { bg: "var(--neutral-tag)", fg: "#FFFFFF" };
}

export function StatusBadge({ status }: { status: string }) {
  const { bg, fg } = toneFor(status);
  const label = status.toLowerCase().replaceAll("_", " ");
  return (

    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[13px] font-normal transition-colors duration-300 ease-out"
      style={{ backgroundColor: bg, color: fg }}
    >
      {label}
    </span>
  );
}

export function ProviderModeBadge({ mode }: { mode: "RAZORPAY_TEST_MODE" | "SIMULATION_MODE" }) {
  const label = mode === "RAZORPAY_TEST_MODE" ? "Razorpay test mode" : "Simulation mode";
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[13px] font-normal border border-[var(--border-strong)]"
      style={{ color: "var(--neutral-tag)" }}
    >
      {label}
    </span>
  );
}
