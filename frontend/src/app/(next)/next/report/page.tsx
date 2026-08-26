"use client";

import { ShieldAlert } from "lucide-react";
import { CustodyRegister } from "@/components/next/report/CustodyRegister";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHasPermission } from "@/hooks/useAuth";

/**
 * Report mode (ARGUS_PLAN.md's redesign Phase 10): findings and custody,
 * built on the real export/custody shape and, since Phase 12, live-wired to
 * it — see CustodyRegister's module note.
 *
 * `entity:read` gates it, same reasoning as Investigate/Triage: investigations
 * and exports each require their own read permission (`export:create` is
 * separately gated inside `CustodyRegister` itself), but every role except
 * administrator holds all of `_READ_INTELLIGENCE` together, so `entity:read`
 * is an accurate single check for whether this mode has anything to show.
 */
export default function NextReportPage() {
  const canReadEntities = useHasPermission("entity:read");

  if (!canReadEntities) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Insufficient permission"
        description="Your role does not include entity:read, so Report mode has nothing to show. This is a permission boundary, not a loading or connectivity failure."
      />
    );
  }

  return <CustodyRegister />;
}
