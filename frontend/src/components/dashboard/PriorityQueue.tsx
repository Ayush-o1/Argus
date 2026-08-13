"use client";

import Link from "next/link";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { useEntities } from "@/hooks/useEntities";
import { RISK_COLORS, riskTier } from "@/lib/theme";
import styles from "./PriorityQueue.module.css";

const TIER_COLOR = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: RISK_COLORS.Low,
  none: RISK_COLORS.Low,
} as const;

/** The dashboard's answer to "where do I start?". Everything else on the page
 * reports what the system knows; this ranks what the analyst should look at
 * next, which is the question a command center actually has to answer. */
export function PriorityQueue({ limit = 8 }: { limit?: number }) {
  const { data, isLoading } = useEntities({ type: "Person", risk_min: 1, page_size: limit });

  if (isLoading) {
    return (
      <div className={styles.list}>
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} height={40} />
        ))}
      </div>
    );
  }

  const entities = data?.data ?? [];
  if (entities.length === 0) {
    return <div className={styles.empty}>No entities currently carry an elevated risk score.</div>;
  }

  return (
    <div className={styles.list}>
      {entities.map((entity, i) => {
        const tier = riskTier(entity.risk_score);
        const color = TIER_COLOR[tier];
        return (
          <Link key={entity.id} href={`/entities/${entity.id}`} className={styles.row}>
            <span className={styles.rank}>{i + 1}</span>
            <span className={styles.icon}>
              <EntityTypeIcon label={entity.label} size={14} />
            </span>
            <span className={styles.body}>
              <div className={styles.name}>{entity.name}</div>
              <div className={styles.meta}>
                {entity.label}
                {entity.properties?.city ? ` · ${entity.properties.city}` : ""}
                {entity.properties?.occupation ? ` · ${entity.properties.occupation}` : ""}
              </div>
            </span>
            <span className={styles.score}>
              <span className={styles.bar}>
                <span
                  className={styles.barFill}
                  style={{ width: `${Math.max(entity.risk_score, 3)}%`, background: color }}
                />
              </span>
              <span className={styles.scoreValue}>{Math.round(entity.risk_score)}</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
