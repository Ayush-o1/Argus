"use client";

import { GlobalActivity } from "@/components/next/command/GlobalActivity";
import { LeadDossier } from "@/components/next/command/LeadDossier";
import { SituationBrief } from "@/components/next/command/SituationBrief";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHasPermission } from "@/hooks/useAuth";
import { useBrowseEntities } from "@/hooks/useEntities";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import { ShieldAlert, Users } from "lucide-react";

const LEAD_TYPES = ["Person", "Organization"];
const LEAD_BAND = "elevated";

/**
 * Command mode (ARGUS_PLAN.md — Phase 3): the operational entry point.
 * Situation brief, global activity, then whatever's selected — falling back
 * to the top elevated lead, matching the real dashboard's own fallback
 * (`app/(app)/dashboard/page.tsx`) and using the same `useBrowseEntities`
 * hook, so the dossier is never an empty column.
 *
 * `entity:read` is checked here, not buried inside a hook, because unlike
 * the old app (whose sidebar hides intelligence-data nav entirely from a
 * role without it — `components/layout/Sidebar.tsx`) every `/next` mode is
 * always in the header nav for every role. An administrator landing here
 * would otherwise see `useDashboardSummary`'s permission-gated query sit
 * disabled forever, rendering as a skeleton that never resolves — which is
 * not "loading", it is "not permitted", and those are different states.
 *
 */
export default function NextCommandPage() {
  const canReadEntities = useHasPermission("entity:read");
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const region = useNextScopeStore((s) => s.region);

  const { data: allLeads, isFetching: loadingLeads } = useBrowseEntities(LEAD_TYPES, LEAD_BAND);

  if (!canReadEntities) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Insufficient permission"
        description="Your role does not include entity:read, so Command mode has nothing to show. This is a permission boundary, not a loading or connectivity failure."
      />
    );
  }

  const leads = region ? allLeads.filter((l) => l.properties.region === region) : allLeads;
  const topLead = leads[0] ?? null;
  const selected = (selectedId ? allLeads.find((l) => l.id === selectedId) : null) ?? topLead;

  return (
    <div>
      <SituationBrief />
      <GlobalActivity />
      {selected ? <LeadDossier subject={selected} /> : !loadingLeads ? (
        <EmptyState icon={Users} title="No elevated leads" description="No entity in scope is currently assessed elevated." />
      ) : null}
    </div>
  );
}
