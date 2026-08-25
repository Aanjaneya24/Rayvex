"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { IconGauge, IconList, IconFlask, IconSettings, IconAlertTriangle, IconMoon, IconSun } from "@tabler/icons-react";
import { setCredentials } from "@/lib/api";

type Mode = "light" | "dark" | null;

function applyMode(mode: Mode) {
  if (mode === null) {
    document.documentElement.removeAttribute("data-mode");
  } else {
    document.documentElement.setAttribute("data-mode", mode);
  }
}

const NAV_ITEMS = [
  { href: "/", label: "Command center", icon: IconGauge },
  { href: "/cases", label: "Cases", icon: IconList },
  { href: "/escalations", label: "Escalations", icon: IconAlertTriangle },
  { href: "/evaluation", label: "Evaluation", icon: IconFlask },
  { href: "/control-center", label: "Control center", icon: IconSettings },
];

const STORAGE_KEY = "rayvex_theme_mode";

export function Sidebar() {
  const pathname = usePathname();
  const [mode, setMode] = useState<Mode>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Mode;
    if (stored === "light" || stored === "dark") {
      setMode(stored);
      applyMode(stored);
    }
  }, []);

  const toggleMode = () => {
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentlyDark = mode === "dark" || (mode === null && systemPrefersDark);
    const next: Mode = currentlyDark ? "light" : "dark";
    setMode(next);
    applyMode(next);
    localStorage.setItem(STORAGE_KEY, next);
  };

  return (
    <aside
      className="fixed left-0 top-0 h-screen w-[240px] border-r border-[var(--border)] bg-[var(--surface-1)] px-4 py-6"
    >
      <div className="mb-8 px-2 text-[18px] font-medium">Rayvex</div>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname?.startsWith(href);
          return (

            <Link
              key={href}
              href={href}
              className="flex items-center gap-2 rounded-full px-3 py-2 text-[14px]"
              style={{
                backgroundColor: active ? "var(--accent-muted)" : "transparent",
                color: active ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              <Icon size={18} stroke={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>
      <button
        className="absolute bottom-14 left-4 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]"
        onClick={toggleMode}
        aria-label="Toggle dark mode"
      >
        {mode === "dark" ? <IconSun size={16} stroke={1.75} /> : <IconMoon size={16} stroke={1.75} />}
        {mode === "dark" ? "Light mode" : "Dark mode"}
      </button>
      <button
        className="absolute bottom-6 left-4 text-[13px] text-[var(--text-secondary)]"
        onClick={() => {
          setCredentials(null);
          window.location.reload();
        }}
      >
        Sign out
      </button>
    </aside>
  );
}
