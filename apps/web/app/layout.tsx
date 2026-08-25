import type { Metadata } from "next";
import { AuthGate } from "@/components/AuthGate";
import { PageFade } from "@/components/PageFade";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rayvex",
  description: "AI revenue recovery infrastructure",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
          <Sidebar />
          <main className="ml-[240px] min-h-screen">
            <div className="mx-auto max-w-[1280px] px-8 py-8">
              <PageFade>{children}</PageFade>
            </div>
          </main>
        </AuthGate>
      </body>
    </html>
  );
}
