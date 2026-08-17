"use client";

import Link from "next/link";
import { useMapRegions } from "@/hooks/useMap";
import { Skeleton } from "@/components/ui/Skeleton";
import { RISK_COLORS } from "@/lib/theme";
import styles from "./GlobalPosture.module.css";

/**
 * Where activity and escalation sit across the world, ranked.
 *
 * The dashboard could report totals and severity bands but had no geographic
 * dimension at all, so it couldn't answer "what is happening globally" or
 * "where is risk concentrated" — two of the questions a command center exists
 * for. Each row is a filtered entry point into the map rather than a static
 * statistic.
 */

const MAX_REGIONS = 6;

export function GlobalPosture() {
  const { data: regions, isLoading } = useMapRegions();

  if (isLoading || !regions) return <Skeleton height={200} />;

  const ranked = [...regions]
    .sort(
      (a, b) =>
        b.elevated_count - a.elevated_count ||
        b.flagged_routes - a.flagged_routes ||
        b.entity_count - a.entity_count,
    )
    .slice(0, MAX_REGIONS);

  // Bars are scaled against the busiest region so differences in volume stay
  // comparable; scaling each row to its own width would make every region look
  // equally active.
  const maxEntities = Math.max(1, ...ranked.map((r) => r.entity_count));

  return (
    <ul className={styles.list}>
      {ranked.map((region) => {
        const accent =
          region.elevated_count >= 4
            ? RISK_COLORS.Critical
            : region.elevated_count >= 1
              ? RISK_COLORS.High
              : "var(--accent-primary)";
        return (
          <li key={region.region}>
            <Link href={`/map?region=${encodeURIComponent(region.region)}`} className={styles.row}>
              <span className={styles.head}>
                <span className={styles.name}>{region.region}</span>
                <span className={styles.stats}>
                  {region.elevated_count > 0 ? (
                    <span className={styles.elevated} style={{ color: accent }}>
                      {region.elevated_count} elevated
                    </span>
                  ) : null}
                  {region.flagged_routes > 0 ? (
                    <span className={styles.routes}>{region.flagged_routes} routes</span>
                  ) : null}
                </span>
              </span>
              <span className={styles.bar}>
                <span
                  className={styles.barFill}
                  style={{
                    width: `${Math.max(3, (region.entity_count / maxEntities) * 100)}%`,
                    background: accent,
                  }}
                />
              </span>
              <span className={styles.meta}>
                {region.entity_count.toLocaleString()} entities · {region.country_count} countries
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
