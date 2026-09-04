"use client";

import { useEffect, useState } from "react";
import { IconLoader2 } from "@tabler/icons-react";
import { api, loadStoredCredentials, setCredentials, setStoredRole } from "@/lib/api";
import { applyMode } from "@/lib/theme";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "authed" | "unauthed">("checking");
  const [mode, setMode] = useState<"sign-in" | "register">("sign-in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const stored = loadStoredCredentials();
    if (stored) verify();
    else setStatus("unauthed");
  }, []);

  useEffect(() => {
    // Login screen is always light. TopNav reclaims theme control once authed.
    if (status === "unauthed") {
      applyMode("light");
    }
  }, [status]);

  const signIn = () => {
    setSubmitting(true);
    setCredentials({ username, password });
    setStatus("checking");
    verify();
  };

  const register = async () => {
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      await api.register(username, password);
      setInfo("Account created — signing you in…");
      setCredentials({ username, password });
      setStatus("checking");
      verify();
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  };

  if (status === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ backgroundColor: "#F7F8FA" }}>
        <div className="flex items-center gap-2 text-[14px]" style={{ color: "#6B7280" }}>
          <IconLoader2 size={16} className="animate-spin" />
          Checking session…
        </div>
      </div>
    );
  }

  if (status === "unauthed") {
    const canSubmit = username.length >= 3 && password.length >= (mode === "register" ? 8 : 1);
    const submit = mode === "register" ? register : signIn;
    return (
      <div
        className="flex min-h-screen items-center justify-center px-4"
        style={{ backgroundColor: "#F7F8FA", color: "#16181D" }}
      >
        <div
          className="animate-card-in flex w-full max-w-sm flex-col gap-3 rounded-card border p-6 shadow-sm"
          style={{ borderColor: "rgba(10,20,40,0.08)", backgroundColor: "#FFFFFF" }}
        >
          <div className="mb-2 text-[18px] font-medium">Rayvex</div>
          <p className="text-[13px]" style={{ color: "#6B7280" }}>
            {mode === "sign-in"
              ? "Viewer role can browse; reviewer role can also act on escalations."
              : "New accounts start as viewer. An existing reviewer can promote you afterward."}
          </p>
          <input
            className="rounded-control border px-3 py-2 text-[14px] outline-none transition-colors focus:border-[#4564DF]"
            style={{ borderColor: "rgba(10,20,40,0.16)", backgroundColor: "#FAFAFB", color: "#16181D" }}
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            type="password"
            className="rounded-control border px-3 py-2 text-[14px] outline-none transition-colors focus:border-[#4564DF]"
            style={{ borderColor: "rgba(10,20,40,0.16)", backgroundColor: "#FAFAFB", color: "#16181D" }}
            placeholder={mode === "register" ? "Password (at least 8 characters)" : "Password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) submit();
            }}
          />
          {error && (
            <div className="animate-message-in text-[13px]" style={{ color: "#C94342" }}>
              {error}
            </div>
          )}
          {info && (
            <div className="animate-message-in text-[13px]" style={{ color: "#188160" }}>
              {info}
            </div>
          )}
          <button
            className="flex items-center justify-center gap-2 rounded-control px-3 py-2 text-[14px] transition-transform active:scale-[0.98] disabled:opacity-50"
            style={{ backgroundColor: "#4564DF", color: "#FFFFFF" }}
            disabled={!canSubmit || submitting}
            onClick={submit}
          >
            {submitting && <IconLoader2 size={14} className="animate-spin" />}
            {mode === "sign-in" ? "Sign in" : "Create account"}
          </button>
          <button
            className="text-[13px] transition-colors hover:opacity-80"
            style={{ color: "#6B7280" }}
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
