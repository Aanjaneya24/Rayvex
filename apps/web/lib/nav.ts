import { IconGauge, IconList, IconFlask, IconSettings, IconAlertTriangle } from "@tabler/icons-react";

export const NAV_ITEMS = [
  { href: "/", label: "Command center", icon: IconGauge },
  { href: "/cases", label: "Cases", icon: IconList },
  { href: "/escalations", label: "Escalations", icon: IconAlertTriangle },
  { href: "/evaluation", label: "Evaluation", icon: IconFlask },
  { href: "/control-center", label: "Control center", icon: IconSettings },
];

export function isNavItemActive(href: string, pathname: string | null): boolean {
  return href === "/" ? pathname === "/" : (pathname?.startsWith(href) ?? false);
}
