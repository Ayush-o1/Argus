"use client";

import { cn } from "@/lib/cn";
import { RISK_COLORS } from "@/lib/theme";
import type { RegionRollup } from "@/hooks/useMap";
import styles from "./RegionStrip.module.css";

/**
 * Regional posture as a *filter*, not a readout.
 *
 * The previous panel listed regions and linked each one away to the map, which
 * made the dashboard a set of exits rather than a workspace. Here a region
 * scopes the lead queue beside it, so "Europe is elevated" becomes a question
 * the analyst can pursue in place: select it, and the queue answers *which*
 * entities are driving it.
 */
export function RegionStrip({
  regions,
  selected,
  onSelect,
}: {
  regions: RegionRollup[];
  selected: string | null;
  onSelect: (region: string | null) => void;
}) {
  const ranked = [...regions].sort(
    (a, b) =>
      b.elevated_count - a.elevated_count ||
      b.anomalous_routes - a.anomalous_routes ||
      b.entity_count - a.entity_count,
  );
  const maxEntities = Math.max(1, ...ranked.map((r) => r.entity_count));

  return (
    <div className={styles.strip} role="group" aria-label="Filter by region">
      <button
        type="button"
        className={cn(styles.cell, styles.allCell, selected === null && styles.cellActive)}
        onClick={() => onSelect(null)}
        aria-pressed={selected === null}
      >
        <span className={styles.name}>All regions</span>
        <span className={styles.meta}>{regions.length} tracked</span>
      </button>

      {ranked.map((region) => {
        const isActive = selected === region.region;
        const accent =
          region.elevated_count >= 4
            ? RISK_COLORS.Critical
            : region.elevated_count >= 1
              ? RISK_COLORS.High
              : "var(--text-quaternary, var(--text-tertiary))";
        return (
          <button
            key={region.region}
            type="button"
            className={cn(styles.cell, isActive && styles.cellActive)}
            onClick={() => onSelect(isActive ? null : region.region)}
            aria-pressed={isActive}
            title={`${region.region} — ${region.entity_count.toLocaleString()} entities, ${region.elevated_count} elevated, ${region.anomalous_routes} anomalous routes`}
          >
            <span className={styles.name}>{region.region}</span>
            <span className={styles.signals}>
              {region.elevated_count > 0 ? (
                <span className={styles.elevated} style={{ color: accent }}>
                  {region.elevated_count}
                </span>
              ) : (
                <span className={styles.quiet}>—</span>
              )}
              {region.anomalous_routes > 0 ? (
                // Spelled out: "21r" saved eight pixels at the cost of the
                // reader knowing what the number counts.
                <span className={styles.routes}>{region.anomalous_routes} routes</span>
              ) : null}
            </span>
            {/* Volume as a hairline: present for comparison, never competing
                with the escalation figure above it. */}
            <span className={styles.bar} aria-hidden>
              <span
                className={styles.barFill}
                style={{ width: `${Math.max(4, (region.entity_count / maxEntities) * 100)}%`, background: accent }}
              />
            </span>
          </button>
        );
      })}
    </div>
  );
}
