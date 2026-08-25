"use client";

import { GlobalActivity } from "@/components/next/command/GlobalActivity";
import { LeadDossier } from "@/components/next/command/LeadDossier";
import { SituationBrief } from "@/components/next/command/SituationBrief";
import { nextFixtureSubjects } from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";

const LEAD_LABELS = new Set(["Person", "Organization"]);

/**
 * Command mode (ARGUS_PLAN.md — Phase 3): the operational entry point.
 * Situation brief, global activity, then whatever's selected — falling back
 * to the top elevated lead, matching the real dashboard's own fallback
 * (`app/(app)/dashboard/page.tsx`), so the dossier is never an empty column.
 */
export default function NextCommandPage() {
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const region = useNextScopeStore((s) => s.region);

  const topLead = [...nextFixtureSubjects]
    .filter((s) => LEAD_LABELS.has(s.label) && s.assessment?.band === "elevated")
    .filter((s) => !region || s.properties.region === region)
    .sort((a, b) => (b.assessment?.score ?? 0) - (a.assessment?.score ?? 0))[0];

  const selected = (selectedId ? nextFixtureSubjects.find((s) => s.id === selectedId) : null) ?? topLead ?? null;

  return (
    <div>
      <SituationBrief />
      <GlobalActivity />
      {selected ? <LeadDossier subject={selected} /> : null}
    </div>
  );
}
