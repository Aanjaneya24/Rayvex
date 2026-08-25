"use client";

import { usePathname } from "next/navigation";

export function PageFade({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="animate-page-fade">
      {children}
    </div>
  );
}
