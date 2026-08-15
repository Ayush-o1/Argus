import { GitCompareArrows } from "lucide-react";
import { describeValue, formatTimestamp, type Conflict } from "@/lib/provenance";
import { KindBadge, SyntheticBadge } from "./KindBadge";
import { RatingBadge } from "./RatingBadge";
import styles from "./provenance.module.css";

/**
 * Two or more contradictory claims, side by side, with no winner.
 *
 * This is the single most important surface in Phase 2, and its design is
 * mostly a list of things it deliberately does not do:
 *
 *   - It does not sort by rating. Ordering is by assertion time, so the layout
 *     carries no opinion.
 *   - It does not widen, highlight or promote any side. The columns are equal
 *     because the interface has no basis for preferring one.
 *   - It does not offer a "resolve" button that picks one. Resolution is a new
 *     assertion by a named person, superseding what it replaces, and both
 *     records survive it.
 *
 * A system that silently picks a side is more dangerous than one that shows the
 * disagreement, because it removes the conflict from the view of the only
 * person qualified to settle it — and does so invisibly, so nobody knows a
 * choice was made at all.
 */
export function ConflictPanel({ conflicts }: { conflicts: Conflict[] }) {
  if (conflicts.length === 0) return null;

  return (
    <>
      {conflicts.map((conflict) => (
        <div key={`${conflict.subject_ref}-${conflict.predicate}`} className={styles.conflict}>
          <div className={styles.conflictHeader}>
            <GitCompareArrows size={15} />
            Sources disagree on <span className={styles.mono}>{conflict.predicate}</span>
            <span className={styles.conflictHeaderNote}>
              {conflict.assertions.length} conflicting claims
            </span>
          </div>

          <div className={styles.conflictSides}>
            {conflict.assertions.map((assertion) => {
              const synthetic = assertion.evidence.some((e) => e.source_is_synthetic);
              return (
                <div key={assertion.assertion_id} className={styles.conflictSide}>
                  <span className={styles.conflictValue}>
                    {describeValue(assertion.object_value)}
                  </span>
                  <div className={styles.conflictMeta}>
                    <KindBadge kind={assertion.epistemic_kind} />
                    <RatingBadge
                      reliability={assertion.rating.reliability}
                      credibility={assertion.rating.credibility}
                    />
                    {synthetic ? <SyntheticBadge /> : null}
                  </div>
                  <div className={styles.conflictAttribution}>
                    {assertion.asserted_by_display} · {assertion.method}
                    <br />
                    Asserted {formatTimestamp(assertion.asserted_at)}
                    {assertion.corroboration &&
                    assertion.corroboration.independent_sources > 0 ? (
                      <>
                        <br />
                        {assertion.corroboration.independent_sources} independent source
                        {assertion.corroboration.independent_sources === 1 ? "" : "s"}
                        {assertion.corroboration.contradicting_observations > 0
                          ? `, ${assertion.corroboration.contradicting_observations} contradicting`
                          : ""}
                      </>
                    ) : null}
                  </div>
                  {assertion.note ? (
                    <div className={styles.conflictAttribution}>{assertion.note}</div>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className={styles.conflictFooter}>
            ARGUS has not chosen between these and will not. Both remain on record with their
            ratings. To resolve it, record your own assessment — it supersedes what it replaces
            without erasing it, so the disagreement stays readable afterwards.
          </div>
        </div>
      ))}
    </>
  );
}
