import type { ReactNode } from "react";
import { AuthGate } from "@/components/auth/AuthGate";
import { NextShell } from "@/components/next/shell/NextShell";

/**
 * Root of the redesigned `/next` experience (ARGUS_PLAN.md — Phase 1).
 *
 * Deliberately does not nest under `(app)/layout.tsx` — it has its own shell
 * entirely (`NextShell`, not the old `AppShell`/`Sidebar`/`Topbar`), so this
 * sits as a sibling route group. `AuthGate` is reused as-is: authentication
 * is real in every phase of this rebuild, even while the intelligence data
 * behind it is fixture-backed — a session that doesn't exist must still be
 * refused here exactly as it is in the old app.
 */
export default function NextLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <NextShell>{children}</NextShell>
    </AuthGate>
  );
}
