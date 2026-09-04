"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { IconMoon, IconRocket, IconSearch, IconSun } from "@tabler/icons-react";
import { failureTypeLabel } from "@/lib/labels";
import { api, CaseSummary, loadStoredCredentials } from "@/lib/api";
import { isNavItemActive, NAV_ITEMS } from "@/lib/nav";
import { useProviderMode } from "@/lib/providerMode";
import { applyMode, loadStoredMode, Mode, THEME_STORAGE_KEY } from "@/lib/theme";

function initialsFor(username: string): string {
  const parts = username.replace(/[._-]+/g, " ").trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const second = parts.length > 1 ? parts[1][0] : parts[0]?.[1] ?? "";
  return (first + second).toUpperCase();
}

function ModePill() {
  const mode = useProviderMode();
  if (mode === null) return null;

  const isSimulation = mode === "SIMULATION_MODE";
  return (
    <div
      className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium"
      style={
        isSimulation
          ? { borderColor: "rgba(160,101,20,0.5)", color: "#E0A94F", backgroundColor: "rgba(160,101,20,0.12)" }
          : { borderColor: "rgba(34,197,94,0.5)", color: "#4ADE80", backgroundColor: "rgba(34,197,94,0.12)" }
      }
      title={
        isSimulation
          ? "This case's payment status came from SimulationProvider, never a real Razorpay call"
          : "This case's payment status came from a real Razorpay Test Mode API call"
      }
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: isSimulation ? "#E0A94F" : "#4ADE80" }}
      />
      {isSimulation ? "SIMULATION" : "TEST"}
    </div>
  );
}

function CaseSearch() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CaseSummary[] | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .listCases({ q: trimmed, limit: 6 })
        .then((r) => setResults(r.cases))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const goToCase = (caseId: string) => {
    router.push(`/cases/${caseId}`);
    setQuery("");
    setResults(null);
    setOpen(false);
  };

  const goToFilteredList = () => {
    if (!query.trim()) return;
    router.push(`/cases?q=${encodeURIComponent(query.trim())}`);
    setOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      (e.target as HTMLInputElement).blur();
    } else if (e.key === "Enter") {
      if (results && results.length === 1) {
        goToCase(results[0].case_id);
      } else {
        goToFilteredList();
      }
    }
  };

  return (
    <div ref={containerRef} className="relative hidden md:block">
      <div
        className="flex items-center gap-2 rounded-full px-3 py-1.5"
        style={{ backgroundColor: "var(--nav-surface)" }}
      >
        <IconSearch size={14} stroke={1.75} style={{ color: "var(--nav-text-secondary)" }} />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search case, payment, order, customer ID"
          className="w-48 bg-transparent text-[13px] outline-none placeholder:text-[var(--nav-text-secondary)]"
          style={{ color: "var(--nav-text)" }}
        />
      </div>

      {open && query.trim().length >= 2 && (
        <div
          className="animate-card-in absolute right-0 top-11 w-96 overflow-hidden rounded-card border shadow-lg"
          style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border-strong)" }}
        >
          {loading && (
            <div className="px-4 py-3 text-[13px] text-[var(--text-muted)]">Searching…</div>
          )}
          {!loading && results && results.length === 0 && (
            <div className="px-4 py-3 text-[13px] text-[var(--text-muted)]">
              No cases match &quot;{query.trim()}&quot;.
            </div>
          )}
          {!loading &&
            results?.map((c) => (
              <button
                key={c.case_id}
                onClick={() => goToCase(c.case_id)}
                className="flex w-full flex-col items-start gap-0.5 border-b border-[var(--border)] px-4 py-2.5 text-left last:border-0 hover:bg-[var(--surface-1)]"
              >
                <span className="text-[13px] font-medium text-[var(--text-primary)]">
                  {c.case_id.slice(0, 8)}… · {c.currency} {c.amount}
                </span>
                <span className="text-[12px] text-[var(--text-muted)]">
                  {failureTypeLabel(c.failure_code)} · {c.status.toLowerCase().replaceAll("_", " ")}
                </span>
              </button>
            ))}
          {!loading && results && results.length > 0 && (
            <button
              onClick={goToFilteredList}
              className="w-full px-4 py-2 text-left text-[13px] text-[var(--accent)] hover:bg-[var(--surface-1)]"
            >
              See all results in Cases →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function TopNav() {
  const pathname = usePathname();
  const [mode, setMode] = useState<Mode>(null);
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    // Reclaims theme control from AuthGate, which forces light mode on the login screen.
    const stored = loadStoredMode();
    setMode(stored);
    applyMode(stored);
    setUsername(loadStoredCredentials()?.username ?? null);
  }, []);

  const toggleMode = () => {
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentlyDark = mode === "dark" || (mode === null && systemPrefersDark);
    const next: Mode = currentlyDark ? "light" : "dark";
    setMode(next);
    applyMode(next);
    localStorage.setItem(THEME_STORAGE_KEY, next);
  };

  const activeItem = NAV_ITEMS.find((item) => isNavItemActive(item.href, pathname));

  return (
    <header
      className="fixed left-0 right-0 top-0 z-20 flex h-14 items-center justify-between px-5"
      style={{ backgroundColor: "var(--nav-bg)", borderBottom: "1px solid var(--nav-border)" }}
    >
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2" style={{ color: "var(--nav-text)" }}>
          <IconRocket size={20} stroke={1.9} style={{ color: "var(--accent)", transform: "rotate(45deg)" }} />
          <span className="text-[16px] font-semibold">Rayvex</span>
        </div>
        {activeItem && (
          <div className="relative hidden items-center sm:flex">
            <span
              aria-hidden
              className="pointer-events-none absolute left-1/2 top-1/2 h-8 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full blur-xl"
              style={{ backgroundColor: "var(--accent)", opacity: 0.25 }}
            />
            <span className="relative text-[13px] font-medium" style={{ color: "var(--nav-text)" }}>
              {activeItem.label}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <ModePill />

        <CaseSearch />

        <button
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{ backgroundColor: "var(--nav-surface)", color: "var(--nav-text-secondary)" }}
          onClick={toggleMode}
          aria-label="Toggle dark mode"
          title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {mode === "dark" ? <IconSun size={16} stroke={1.75} /> : <IconMoon size={16} stroke={1.75} />}
        </button>

        {username && (
          <div
            title={`Signed in as ${username}`}
            className="flex h-8 w-8 items-center justify-center rounded-full text-[12px] font-medium"
            style={{ backgroundColor: "var(--accent)", color: "var(--on-accent)" }}
          >
            {initialsFor(username)}
          </div>
        )}
      </div>
    </header>
  );
}
