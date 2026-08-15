import type { ReactNode } from "react";
import { AuthGate } from "@/components/auth/AuthGate";
import { RouteGuard } from "@/components/auth/RouteGuard";
import { AppShell } from "@/components/layout/AppShell";

export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <AppShell>
        <RouteGuard>{children}</RouteGuard>
      </AppShell>
    </AuthGate>
  );
}
