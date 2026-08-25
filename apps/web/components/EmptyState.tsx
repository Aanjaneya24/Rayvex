import type { Icon as TablerIcon } from "@tabler/icons-react";

export function EmptyState({
  icon: Icon,
  heading,
  subtext,
  action,
}: {
  icon: TablerIcon;
  heading: string;
  subtext?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <Icon size={40} stroke={1.5} style={{ color: "var(--text-muted)" }} />
      <div className="text-[16px] font-medium text-[var(--text-primary)]">{heading}</div>
      {subtext && (
        <p className="max-w-sm text-[13px] text-[var(--text-secondary)]">{subtext}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-1 rounded-control bg-[var(--accent)] px-4 py-1.5 text-[14px] text-[var(--on-accent)]"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
