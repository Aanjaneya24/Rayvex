export type Mode = "light" | "dark" | null;

export const THEME_STORAGE_KEY = "rayvex_theme_mode";

// null removes the explicit override, falling back to prefers-color-scheme.
export function applyMode(mode: Mode) {
  if (mode === null) {
    document.documentElement.removeAttribute("data-mode");
  } else {
    document.documentElement.setAttribute("data-mode", mode);
  }
}

export function loadStoredMode(): Mode {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}
