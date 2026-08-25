"use client";

import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { EvidenceLedger } from "@/components/next/evidence/EvidenceLedger";
import { nextFixtureProvenance, nextFixtureSubjects } from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./page.module.css";

const LEAD_LABELS = new Set(["Person", "Organization"]);

/**
 * Evidence mode (ARGUS_PLAN.md's redesign Phase 8): provenance, reliability
 * and contradiction for whichever subject is in scope — same fallback as
 * Command's dossier (falls back to the top elevated lead so this is never an
 * empty page), so arriving here without first clicking a subject elsewhere
 * still shows something real rather than a blank state.
 */
export default function NextEvidencePage() {
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);
  const region = useNextScopeStore((s) => s.region);

  const topLead = [...nextFixtureSubjects]
    .filter((s) => LEAD_LABELS.has(s.label) && s.assessment?.band === "elevated")
    .filter((s) => !region || s.properties.region === region)
    .sort((a, b) => (b.assessment?.score ?? 0) - (a.assessment?.score ?? 0))[0];

  const selected = (selectedId ? nextFixtureSubjects.find((s) => s.id === selectedId) : null) ?? topLead ?? null;

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
            {nextFixtureSubjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className={styles.body}>
        <EvidenceLedger provenance={selected ? (nextFixtureProvenance[selected.id] ?? null) : null} />
      </div>
    </div>
  );
}
