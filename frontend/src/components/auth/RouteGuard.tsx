"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSession } from "@/hooks/useAuth";
import { NAV_GROUPS } from "@/lib/constants";

/**
 * Renders an explanation instead of a surface the signed-in role cannot use.
 *
 * Without this, an administrator — who deliberately holds no intelligence-read
 * permission — landed on the dashboard and saw loading skeletons that never
 * resolved, because every underlying query returned 403. A permission boundary
 * should read as a boundary, not as a system that is broken or still thinking.
 *
 * This is presentation only. The server enforces the same permission on every
 * request; this exists so the denial is legible.
 */
/** "an analyst" / "an administrator" / "an auditor", but "a viewer". */
function article(role: string | undefined): string {
  return role && /^[aeiou]/i.test(role) ? "an" : "a";
}

export function RouteGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: session } = useSession();

  const item = NAV_GROUPS.flatMap((group) => group.items).find(
    (candidate) => pathname === candidate.href || pathname.startsWith(`${candidate.href}/`),
  );

  const required = item?.permission;
  const allowed = !required || (session?.permissions.includes(required) ?? false);
  if (allowed) return <>{children}</>;

  // Somewhere this role can actually go, so the dead end has an exit.
  const reachable = NAV_GROUPS.flatMap((group) => group.items).find(
    (candidate) => !candidate.permission || (session?.permissions.includes(candidate.permission) ?? false),
  );

  return (
    <EmptyState
      icon={Lock}
      title={`${item?.label ?? "This page"} is not available to your role`}
      description={
        `Your account is ${article(session?.user.role)} ${session?.user.role ?? "user"}, which does not hold the ` +
        `"${required}" permission. This is a deliberate restriction, not a fault — ` +
        `an administrator manages the system rather than reading intelligence, and an ` +
        `auditor reads records rather than changing them.`
      }
      actions={
        reachable ? (
          <Link href={reachable.href} style={{ textDecoration: "none" }}>
            Go to {reachable.label}
          </Link>
        ) : null
      }
    />
  );
}
