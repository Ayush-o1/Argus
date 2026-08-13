"use client";

import Link from "next/link";
import { RISK_COLORS as COLORS } from "@/lib/theme";
import type { Severity } from "@/lib/types";
import styles from "./RiskDonut.module.css";

interface RiskBreakdownProps {
  data: { level: Severity; count: number }[];
}

const RISK_FLOOR: Record<Severity, number> = { Critical: 80, High: 60, Medium: 35, Low: 0 };

function formatShare(count: number, total: number): string {
  if (total === 0) return "0%";
  const pct = (count / total) * 100;
  if (count === 0) return "0%";
  // A population where >99% sits in one band rounds every meaningful band to
  // "0%", which reads as "there is nothing here" — exactly backwards for the
  // handful of entities an analyst actually needs to see.
  if (pct < 0.1) return "<0.1%";
  if (pct < 1) return `${pct.toFixed(1)}%`;
  return `${pct.toFixed(0)}%`;
}

/** Severity ladder rather than a pie. With ~99.8% of the population in the
 * lowest band, a proportional chart renders as one flat colour and hides the
 * few entities that matter; a ranked ladder keeps the elevated bands legible
 * and makes each one a direct entry point into a filtered search. */
export function RiskDonut({ data }: RiskBreakdownProps) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  // Scale bars against the largest *elevated* band so Critical/High/Medium stay
  // comparable to each other instead of all collapsing next to a 3992-wide Low.
  const elevatedMax = Math.max(...data.filter((d) => d.level !== "Low").map((d) => d.count), 1);

  return (
    <div className={styles.ladder}>
      {data.map((entry) => {
        const isLow = entry.level === "Low";
        const width = isLow ? 100 : Math.max((entry.count / elevatedMax) * 100, entry.count > 0 ? 8 : 0);
        return (
          <Link
            key={entry.level}
            href={`/search?risk=${RISK_FLOOR[entry.level]}`}
            className={styles.row}
            title={`Browse entities scoring ${RISK_FLOOR[entry.level]} and above`}
          >
            <span className={styles.rowHead}>
              <span className={styles.dot} style={{ background: COLORS[entry.level] }} />
              <span className={styles.level}>{entry.level}</span>
            </span>
            <span className={styles.track}>
              <span className={styles.fill} style={{ width: `${width}%`, background: COLORS[entry.level] }} />
            </span>
            <span className={styles.count}>{entry.count.toLocaleString("en-IN")}</span>
            <span className={styles.share}>{formatShare(entry.count, total)}</span>
          </Link>
        );
      })}
    </div>
  );
}
