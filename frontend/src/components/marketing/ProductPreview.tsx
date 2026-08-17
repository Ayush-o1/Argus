"use client";

import { useDashboardSummary } from "@/hooks/useDashboard";
import { formatScore } from "@/lib/assessment";
import { useMapRegions } from "@/hooks/useMap";
import { useBrowseEntities } from "@/hooks/useEntities";
import { RISK_COLORS } from "@/lib/theme";
import styles from "./ProductPreview.module.css";

/**
 * The hero visual: the actual product, on live data.
 *
 * This replaced an abstract constellation of dots and lines — a decoration
 * that could have fronted any product. A visitor should understand what ARGUS
 * is by looking at it, so this renders the real Command Center composition
 * (situation statement, regional posture, ranked leads) against the same
 * running instance the "Enter Argus" button leads to. The numbers move because
 * they are the dataset's numbers, not because they are animated.
 */

const REGION_ROWS = 5;
const LEAD_ROWS = 4;

export function ProductPreview() {
  const { data: summary } = useDashboardSummary();
  const { data: regions } = useMapRegions();
  const { data: leads } = useBrowseEntities(["Person", "Organization"], "elevated");

  const rankedRegions = [...(regions ?? [])]
    .sort((a, b) => b.elevated_count - a.elevated_count || b.flagged_routes - a.flagged_routes)
    .slice(0, REGION_ROWS);
  const maxEntities = Math.max(1, ...rankedRegions.map((r) => r.entity_count));
  const topLeads = (leads ?? []).slice(0, LEAD_ROWS);

  const elevated = summary?.elevated_entities ?? 0;
  const leadRegion = rankedRegions[0]?.region;

  return (
    <div className={styles.frame} aria-hidden>
      <div className={styles.chrome}>
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.chromeLabel}>Command Center</span>
      </div>

      <div className={styles.body}>
        <p className={styles.statement}>
          <strong>{elevated || "—"}</strong> entities ARGUS assessed as warranting review
          {leadRegion ? (
            <>
              , concentrated in <strong>{leadRegion}</strong>
            </>
          ) : null}
          . <strong>{summary?.open_alerts ?? "—"}</strong> alerts open.
        </p>

        <div className={styles.regions}>
          {rankedRegions.map((region) => {
            const accent =
              region.elevated_count >= 4
                ? RISK_COLORS.Critical
                : region.elevated_count >= 1
                  ? RISK_COLORS.High
                  : "var(--accent-primary)";
            return (
              <div key={region.region} className={styles.regionCell}>
                <span className={styles.regionName}>{region.region}</span>
                <span className={styles.regionValue} style={{ color: accent }}>
                  {region.elevated_count || "—"}
                </span>
                <span className={styles.regionBar}>
                  <span
                    className={styles.regionBarFill}
                    style={{
                      width: `${Math.max(6, (region.entity_count / maxEntities) * 100)}%`,
                      background: accent,
                    }}
                  />
                </span>
              </div>
            );
          })}
        </div>

        <div className={styles.leads}>
          <span className={styles.leadsTitle}>Leads</span>
          {topLeads.map((lead) => (
            <div key={lead.uuid} className={styles.leadRow}>
              <span className={styles.leadName}>{lead.name}</span>
              <span className={styles.leadPlace}>
                {[lead.properties.city ?? lead.properties.registered_city, lead.properties.country]
                  .filter(Boolean)
                  .join(", ")}
              </span>
              <span className={styles.leadScore}>{formatScore(lead.assessment?.score) ?? "—"}</span>
            </div>
          ))}
          {topLeads.length === 0
            ? Array.from({ length: LEAD_ROWS }).map((_, i) => <div key={i} className={styles.leadSkeleton} />)
            : null}
        </div>
      </div>
    </div>
  );
}
