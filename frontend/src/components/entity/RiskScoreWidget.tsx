import { KindBadge, SyntheticBadge } from "@/components/provenance/KindBadge";
import { RatingBadge } from "@/components/provenance/RatingBadge";
import { riskLevelFromScore } from "@/components/ui/RiskBadge";
import type { AttributeProvenance } from "@/lib/provenance";
import styles from "./RiskScoreWidget.module.css";

const FILL_COLOR: Record<string, string> = {
  critical: "var(--risk-critical)",
  high: "var(--risk-high)",
  medium: "var(--risk-medium)",
  low: "var(--risk-low)",
  unknown: "var(--risk-unknown)",
};

/**
 * The risk figure, shown with what it actually is.
 *
 * This number is the audit's headline finding. The scenario generator assigns
 * it from storyline membership — from its own answer key — and nothing in the
 * backend has ever recomputed it. Displayed as a bare score with a coloured
 * bar, it reads as an analytic conclusion, so an analyst who follows it to a
 * planted storyline concludes the system found something when the system
 * displayed the answer.
 *
 * The fix here is not a warning string. The widget reads the risk value's
 * assertion from the provenance store and renders whatever that assertion
 * actually says: its epistemic kind, its rating, its method, and its stated
 * basis. When Phase 5 replaces the generator's number with a derived, calibrated
 * assessment, this component will show *that* — same code, different truth,
 * because it displays the provenance rather than a hardcoded caveat about it.
 */
export function RiskScoreWidget({
  score,
  factors,
  provenance,
}: {
  score: number;
  factors: string[];
  provenance?: AttributeProvenance;
}) {
  const level = riskLevelFromScore(score);
  const color = FILL_COLOR[level];
  const assertion = provenance?.assertions[0];
  const synthetic =
    provenance?.observations.some((o) => o.source_is_synthetic) ||
    assertion?.evidence.some((e) => e.source_is_synthetic) ||
    false;

  return (
    <div className={styles.wrap}>
      <div className={styles.scoreRow}>
        <span className={styles.scoreValue} style={{ color }}>
          {score.toFixed(0)}
        </span>
        <span className={styles.scoreMax}>/ 100</span>
      </div>
      <div className={styles.track}>
        <div className={styles.fill} style={{ width: `${score}%`, background: color }} />
      </div>

      {/* Sits directly under the number rather than behind a tab. A caveat one
          click away from a figure this prominent is a caveat nobody reads. */}
      {provenance ? (
        <div className={styles.provenanceRow}>
          <KindBadge kind={assertion ? assertion.epistemic_kind : provenance.kind} />
          {assertion ? (
            <RatingBadge
              reliability={assertion.rating.reliability}
              credibility={assertion.rating.credibility}
            />
          ) : null}
          {synthetic ? <SyntheticBadge /> : null}
        </div>
      ) : null}

      {assertion ? (
        <p className={styles.basis}>
          {assertion.note ?? `Derived by ${assertion.method}.`}
        </p>
      ) : null}

      {factors.length > 0 ? (
        <div className={styles.factors}>
          <span className={styles.factorTitle}>Contributing Factors</span>
          {factors.map((factor) => (
            <div key={factor} className={styles.factorRow}>
              {factor}
            </div>
          ))}
        </div>
      ) : (
        <p style={{ fontSize: 13, color: "var(--text-tertiary)" }}>No risk factors on record.</p>
      )}
    </div>
  );
}
