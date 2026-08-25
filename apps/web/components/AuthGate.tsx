"use client";

import { useEffect, useState } from "react";
import { api, loadStoredCredentials, setCredentials } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "authed" | "unauthed">("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const verify = async () => {
    try {
      await api.getMetricsSummary();
      setStatus("authed");
      setError(null);
    } catch (e) {
      setCredentials(null);
      setStatus("unauthed");
      setError(String(e));
    }
  };

  useEffect(() => {
    const stored = loadStoredCredentials();
    if (stored) verify();
    else setStatus("unauthed");
  }, []);

  if (status === "checking") {
    return <div className="p-8 text-[14px] text-[var(--text-muted)]">Checking session…</div>;
  }

  if (status === "unauthed") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex w-full max-w-sm flex-col gap-3 rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-6">
          <div className="mb-2 text-[18px] font-medium">Rayvex</div>
          <p className="text-[13px] text-[var(--text-secondary)]">
            Viewer role can browse; reviewer role can also act on escalations.
          </p>
          <input
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-2 text-[14px]"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            type="password"
            className="rounded-control border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 py-2 text-[14px]"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && username && password) {
                setCredentials({ username, password });
                setStatus("checking");
                verify();
              }
            }}
          />
          {error && <div className="text-[13px] text-[var(--danger-text)]">Sign-in failed: {error}</div>}
          <button
            className="rounded-control bg-[var(--accent)] px-3 py-2 text-[14px] text-[var(--on-accent)] disabled:opacity-50"
            disabled={!username || !password}
            onClick={() => {
              setCredentials({ username, password });
              setStatus("checking");
              verify();
            }}
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
