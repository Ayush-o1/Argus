import { Check, Equal, Minus, X } from "lucide-react";
import type { AttributeComparison, Verdict } from "@/lib/resolution";
import { VERDICT_LABEL, formatValue } from "@/lib/resolution";
import styles from "./resolution.module.css";

const ICONS: Record<Verdict, typeof Check> = {
  agree: Check,
  partial: Equal,
  disagree: X,
  not_comparable: Minus,
};

/**
 * Why two records were matched — every attribute the model looked at, side by
 * side, in one place.
 *
 * The design decision that matters is that **`not_comparable` is a visible
 * state, not a blank cell.** A row showing "Date of birth — not comparable"
 * tells an analyst that ARGUS has no information either way. A blank row, or a
 * row quietly omitted, tells them nothing and reads as agreement by default.
 *
 * Disagreements are listed first for the same reason: a review screen that
 * leads with everything that matched is a screen arguing for the merge, and
 * the analyst's job is to be able to argue the other way.
 */
export function ComparisonTable({
  comparisons,
  leftRef,
  rightRef,
}: {
  comparisons: AttributeComparison[];
  leftRef: string;
  rightRef: string;
}) {
  const order: Record<Verdict, number> = {
    disagree: 0,
    partial: 1,
    agree: 2,
    not_comparable: 3,
  };
  const sorted = [...comparisons].sort(
    (a, b) => order[a.verdict] - order[b.verdict] || b.weight - a.weight,
  );

  return (
    <table className={styles.comparison}>
      <thead>
        <tr>
          <th scope="col">Attribute</th>
          <th scope="col">{leftRef}</th>
          <th scope="col">{rightRef}</th>
          <th scope="col">Verdict</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((comparison) => {
          const Icon = ICONS[comparison.verdict];
          return (
            <tr key={comparison.key} className={styles[`row_${comparison.verdict}`]}>
              <th scope="row" className={styles.attributeName}>
                {comparison.label}
                {/* The weight is shown because the score is a weighted mean —
                    without it, "name agrees" and "colour agrees" look like
                    equally strong evidence. */}
                <span className={styles.weight}>×{comparison.weight}</span>
              </th>
              <td className={styles.value}>{formatValue(comparison.left)}</td>
              <td className={styles.value}>{formatValue(comparison.right)}</td>
              <td className={styles.verdict}>
                <Icon size={14} strokeWidth={2} />
                <span>{VERDICT_LABEL[comparison.verdict]}</span>
                {comparison.score !== null && comparison.verdict !== "not_comparable" ? (
                  <span className={styles.subScore}>{comparison.score.toFixed(2)}</span>
                ) : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
