"use client";

import { ShieldAlert } from "lucide-react";
import { InvestigateWorkspace } from "@/components/next/investigate/InvestigateWorkspace";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHasPermission } from "@/hooks/useAuth";

/**
 * Investigate mode (ARGUS_PLAN.md Phase 5-7): Graph, Map and Timeline as
 * three lenses over one shared scope, rather than three separate pages.
 *
 * `entity:read` gates every lens here (graph/map both actually require
 * `graph:read`, alerts/investigations elsewhere require their own read
 * permissions, but the real role table bundles all intelligence-read
 * permissions together for every role except administrator — see
 * `roles.py`'s `_READ_INTELLIGENCE` — so `entity:read` alone is an accurate
 * proxy, matching Command mode's own gate). Without this, an administrator
 * landing here would see every lens's query sit permanently disabled,
 * rendering as a skeleton that never resolves.
 */
export default function NextInvestigatePage() {
  const canReadEntities = useHasPermission("entity:read");

  if (!canReadEntities) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Insufficient permission"
        description="Your role does not include entity:read, so Investigate mode has nothing to show. This is a permission boundary, not a loading or connectivity failure."
      />
    );
  }

  return <InvestigateWorkspace />;
}
