"use client";

import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { EvidenceLedger } from "@/components/next/evidence/EvidenceLedger";
import { useHasPermission } from "@/hooks/useAuth";
import { useBrowseEntities } from "@/hooks/useEntities";
import { useSubjectProvenance } from "@/hooks/useProvenance";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import { ShieldAlert, Users } from "lucide-react";
import styles from "./page.module.css";

const LEAD_TYPES = ["Person", "Organization"];
const LEAD_BAND = "elevated";

/**
 * Evidence mode (ARGUS_PLAN.md's redesign Phase 8): provenance, reliability
 * and contradiction for whichever subject is in scope — same fallback as
 * Command's dossier (falls back to the top elevated lead so this is never an
 * empty page).
 *
 * Live-wired (Phase 12): `useBrowseEntities` (same call Command makes — the
 * same query key, so React Query serves this from the same cache rather
 * than refetching) supplies the subject picker and fallback lead;
 * `useSubjectProvenance` is the real hook `ProvenancePanel` uses on the live
 * entity detail page. `EvidenceLedger` itself needed no changes — it was
 * already typed against `SubjectProvenance`, not the fixture.
 *
 * Every hook here runs unconditionally on every render — permission and
 * "nothing selected yet" are branches in the JSX, not early returns before
 * other hooks, so which hooks run never depends on a value that could
 * change without a remount (rules-of-hooks).
 */
export default function NextEvidencePage() {
  const canReadEntities = useHasPermission("entity:read");
  const canReadProvenance = useHasPermission("provenance:read");
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);
  const region = useNextScopeStore((s) => s.region);

  const { data: allLeads, isFetching: loadingLeads } = useBrowseEntities(LEAD_TYPES, LEAD_BAND);

  const leads = region ? allLeads.filter((l) => l.properties.region === region) : allLeads;
  const topLead = leads[0] ?? null;
  const selected = (selectedId ? allLeads.find((l) => l.id === selectedId) : null) ?? topLead;

  const { data: provenance, isLoading: provenanceLoading } = useSubjectProvenance(selected?.id, null);

  if (!canReadEntities) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Insufficient permission"
        description="Your role does not include entity:read, so Evidence mode has nothing to show."
      />
    );
  }

  return (
    <div className={styles.wrap}>
      {selected ? (
        <div className={styles.header}>
          <span className={styles.headerLabel}>EVIDENCE</span>
          <div className={styles.headerDivider} />
          <span className={styles.headerTitle}>{selected.name}</span>
          <AssessmentBadge assessment={selected.assessment} />
          <div className={styles.headerSpacer} />
          <select
            className={styles.subjectPicker}
            value={selected.id}
            onChange={(e) => select(e.target.value)}
            aria-label="Subject"
          >
            {leads.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className={styles.body}>
        {!selected ? (
          loadingLeads ? (
            <Skeleton height={200} />
          ) : (
            <EmptyState icon={Users} title="No elevated leads" description="No entity in scope is currently assessed elevated." />
          )
        ) : !canReadProvenance ? (
          <EmptyState icon={ShieldAlert} title="Insufficient permission" description="Your role does not include provenance:read." />
        ) : provenanceLoading ? (
          <Skeleton height={200} />
        ) : (
          <EvidenceLedger provenance={provenance ?? null} />
        )}
      </div>
    </div>
  );
}
