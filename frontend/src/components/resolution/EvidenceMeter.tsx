import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/resolution";
import styles from "./resolution.module.css";

/**
 * A score and the evidence it was computed from, always together.
 *
 * 0.94 from two attributes out of nine is a different claim from 0.94 from
 * eight, and a surface that shows only the first number invites the reader to
 * treat them as the same. This is the same rule the rest of ARGUS follows for
 * aggregates: no figure without its denominator.
 */
export function EvidenceMeter({
  score,
  evidenceWeight,
  className,
}: {
  score: number | null;
  evidenceWeight: number;
  className?: string;
}) {
  const percent = Math.round(evidenceWeight * 100);
  const thin = evidenceWeight < 0.45;

  return (
    <div className={cn(styles.meter, className)}>
      <div className={styles.meterScore}>{formatScore(score)}</div>
      <div className={styles.meterBody}>
        <div className={styles.meterTrack}>
          <div
            className={cn(styles.meterFill, thin && styles.meterFillThin)}
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className={styles.meterLabel}>
          {percent}% of the model&rsquo;s evidence was comparable
        </div>
      </div>
    </div>
  );
}
