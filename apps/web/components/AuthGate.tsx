"use client";

import { useEffect, useState } from "react";
import { api, loadStoredCredentials, setCredentials, setStoredRole } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "authed" | "unauthed">("checking");
  const [mode, setMode] = useState<"sign-in" | "register">("sign-in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const verify = async () => {
    try {
      const me = await api.me();
      setStoredRole(me.role);
      setStatus("authed");
      setError(null);
    } catch (e) {
      setCredentials(null);
      setStoredRole(null);
      setStatus("unauthed");
      setError(String(e));
    }
  };

  useEffect(() => {
    const stored = loadStoredCredentials();
    if (stored) verify();
    else setStatus("unauthed");
  }, []);

  const signIn = () => {
    setCredentials({ username, password });
    setStatus("checking");
    verify();
  };

  const register = async () => {
    setError(null);
    setInfo(null);
    try {
      await api.register(username, password);
      setInfo("Account created — signing you in…");
      signIn();
    } catch (e) {
      setError(String(e));
    }
  };

  if (status === "checking") {
    return <div className="p-8 text-[14px] text-[var(--text-muted)]">Checking session…</div>;
  }

  if (status === "unauthed") {
    const canSubmit = username.length >= 3 && password.length >= (mode === "register" ? 8 : 1);
    const submit = mode === "register" ? register : signIn;
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex w-full max-w-sm flex-col gap-3 rounded-card border border-[var(--border)] bg-[var(--surface-2)] p-6">
          <div className="mb-2 text-[18px] font-medium">Rayvex</div>
          <p className="text-[13px] text-[var(--text-secondary)]">
            {mode === "sign-in"
              ? "Viewer role can browse; reviewer role can also act on escalations."
              : "New accounts start as viewer. An existing reviewer can promote you afterward."}
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
            placeholder={mode === "register" ? "Password (at least 8 characters)" : "Password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) submit();
            }}
          />
          {error && <div className="text-[13px] text-[var(--danger-text)]">{error}</div>}
          {info && <div className="text-[13px] text-[var(--success-text)]">{info}</div>}
          <button
            className="rounded-control bg-[var(--accent)] px-3 py-2 text-[14px] text-[var(--on-accent)] disabled:opacity-50"
            disabled={!canSubmit}
            onClick={submit}
          >
            {mode === "sign-in" ? "Sign in" : "Create account"}
          </button>
          <button
            className="text-[13px] text-[var(--text-secondary)]"
            onClick={() => {
              setMode(mode === "sign-in" ? "register" : "sign-in");
              setError(null);
              setInfo(null);
            }}
          >
            {mode === "sign-in" ? "New here? Create an account" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
