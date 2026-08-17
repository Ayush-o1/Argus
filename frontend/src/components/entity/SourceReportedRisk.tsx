import { KindBadge, SyntheticBadge } from "@/components/provenance/KindBadge";
import { RatingBadge } from "@/components/provenance/RatingBadge";
import type { AttributeProvenance } from "@/lib/provenance";
import styles from "./SourceReportedRisk.module.css";

/**
 * A risk figure *a source claimed*, shown as a claim.
 *
 * This component was `RiskScoreWidget`, and it rendered the number the scenario
 * generator assigns from storyline membership — its own answer key — as the
 * headline attribute of every entity. Phase 2 attached the provenance so the
 * number could no longer be displayed without what it actually was. Phase 5
 * finished the job: ARGUS now computes its own assessment, that assessment is
 * the headline, and this is what remains — a source's reported value, kept
 * because deleting it would destroy a claim the provenance store holds an
 * assertion about.
 *
 * The value is read from the assertion rather than from the node. That is the
 * point: what is displayed here is only ever something a named source said, at
 * a stated time, with a stated basis. There is no code path by which a bare
 * property reaches this component.
 */
export function SourceReportedRisk({ provenance }: { provenance: AttributeProvenance }) {
  const assertion = provenance.assertions[0];
  if (!assertion) return null;

  const value = typeof assertion.object_value === "number" ? assertion.object_value : null;
  const synthetic =
    provenance.observations.some((o) => o.source_is_synthetic) ||
    assertion.evidence.some((e) => e.source_is_synthetic) ||
    false;

  return (
    <div className={styles.wrap}>
      <div className={styles.scoreRow}>
        <span className={styles.scoreValue}>{value === null ? "—" : value.toFixed(0)}</span>
        <span className={styles.scoreMax}>/ 100, as reported</span>
      </div>

      <div className={styles.provenanceRow}>
        <KindBadge kind={assertion.epistemic_kind} />
        <RatingBadge
          reliability={assertion.rating.reliability}
          credibility={assertion.rating.credibility}
        />
        {synthetic ? <SyntheticBadge /> : null}
      </div>

      <p className={styles.basis}>{assertion.note ?? `Derived by ${assertion.method}.`}</p>

      <p className={styles.disclaimer}>
        This is a value a source supplied, not a conclusion ARGUS reached. Nothing on this page or
        anywhere else in the product is computed from it.
      </p>
    </div>
  );
}
