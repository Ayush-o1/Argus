import { riskLevelFromScore } from "@/components/ui/RiskBadge";
import styles from "./RiskScoreWidget.module.css";

const FILL_COLOR: Record<string, string> = {
  critical: "var(--risk-critical)",
  high: "var(--risk-high)",
  medium: "var(--risk-medium)",
  low: "var(--risk-low)",
  unknown: "var(--risk-unknown)",
};

export function RiskScoreWidget({ score, factors }: { score: number; factors: string[] }) {
  const level = riskLevelFromScore(score);
  const color = FILL_COLOR[level];

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
