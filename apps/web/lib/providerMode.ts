"use client";

import { useEffect, useState } from "react";

// Cross-component signal for the top nav's provider mode pill — reuses
// the mode already present in case detail's verification_proof rather
// than a new endpoint. Only populated while a case detail page is open.

export type ProviderMode = "RAZORPAY_TEST_MODE" | "SIMULATION_MODE";

const EVENT_NAME = "rayvex:provider-mode";
let current: ProviderMode | null = null;

export function reportProviderMode(mode: ProviderMode | null) {
  current = mode;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ProviderMode | null>(EVENT_NAME, { detail: mode }));
  }
}

export function useProviderMode(): ProviderMode | null {
  const [mode, setMode] = useState<ProviderMode | null>(current);
  useEffect(() => {
    setMode(current);
    const handler = (e: Event) => setMode((e as CustomEvent<ProviderMode | null>).detail);
    window.addEventListener(EVENT_NAME, handler);
    return () => window.removeEventListener(EVENT_NAME, handler);
  }, []);
  return mode;
}
