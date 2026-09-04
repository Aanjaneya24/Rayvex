"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconLogout } from "@tabler/icons-react";
import { setCredentials, setStoredRole } from "@/lib/api";
import { isNavItemActive, NAV_ITEMS } from "@/lib/nav";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="fixed left-0 top-14 h-[calc(100vh-56px)] w-[240px] border-r border-[var(--border)] bg-[var(--surface-1)] px-3 py-5"
    >
      <div className="mb-2 px-3 text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
        Recovery
      </div>
      <nav className="flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isNavItemActive(href, pathname);
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2.5 rounded-control px-3 py-2 text-[14px] transition-colors duration-150"
              style={{
                backgroundColor: active ? "var(--sidebar-active-bg)" : "transparent",
                color: active ? "var(--text-primary)" : "var(--text-secondary)",
                fontWeight: active ? 600 : 400,
              }}
            >
              <Icon size={18} stroke={active ? 2 : 1.75} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="absolute bottom-0 left-0 right-0 border-t border-[var(--border)] px-3 py-4">
        <button
          className="flex w-full items-center gap-2.5 rounded-control px-3 py-2 text-[13px] text-[var(--text-secondary)] hover:bg-[var(--sidebar-active-bg)]"
          onClick={() => {
            setCredentials(null);
            setStoredRole(null);
            window.location.reload();
          }}
        >
          <IconLogout size={16} stroke={1.75} />
          Sign out
        </button>
      </div>
    </aside>
  );
}
