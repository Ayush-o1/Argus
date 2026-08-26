"use client";

import { ShieldAlert } from "lucide-react";
import { TriageQueues } from "@/components/next/triage/TriageQueues";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHasPermission } from "@/hooks/useAuth";

/**
 * Triage mode (ARGUS_PLAN.md's redesign Phase 9): Alerts and the
 * investigation queue as working queues, with Cases kept visibly separate.
 *
 * `entity:read` gates it, same reasoning as Investigate mode: alerts,
 * investigations and cases each require their own read permission, but
 * every role except administrator holds all of them together (`roles.py`'s
 * `_READ_INTELLIGENCE`), so `entity:read` is an accurate single check.
 */
export default function NextTriagePage() {
  const canReadEntities = useHasPermission("entity:read");

  if (!canReadEntities) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Insufficient permission"
        description="Your role does not include entity:read, so Triage mode has nothing to show. This is a permission boundary, not a loading or connectivity failure."
      />
    );
  }

  return <TriageQueues />;
}
