"use client";

import { useMemo } from "react";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useBrowseEntities } from "@/hooks/useEntities";
import { bandColorVar, formatAgo, severityColorVar } from "@/lib/next/format";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./LeadsIncidentsPanel.module.css";

const LEAD_TYPES = ["Person", "Organization"];
const LEAD_BAND = "elevated";
const MAX_LEADS = 25;

function inWindow(iso: string, window: { start: number; end: number } | null): boolean {
  if (!window) return true;
  const t = Date.parse(iso);
  return t >= Math.min(window.start, window.end) && t <= Math.max(window.start, window.end);
}

/**
 * Elevated leads + recent incidents — the same panel content whether it's
 * docked (desktop) or a slide-over sheet (compact layout).
 *
 * Live-wired (Phase 12): leads use `useBrowseEntities`, same as every other
 * mode's lead list. Incidents use `useDashboardSummary().recent_incidents`
 * (shares its cache entry with Command/the shell — no extra request) rather
 * than a dedicated feed, because none exists: the only other `Incident[]`
 * source in this app is per-entity (`useEntityAlerts`). That real payload
 * has no `involved_entity_ids`, unlike the fixture's, so — honestly, not
 * silently — incident rows are no longer clickable-to-a-subject, and the
 * list is a bounded "recent" set filtered by time window only; region
 * cannot narrow it without an entity link the API doesn't return.
 */
export function LeadsIncidentsPanel() {
  const region = useNextScopeStore((s) => s.region);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);

  const { data: allLeads } = useBrowseEntities(LEAD_TYPES, LEAD_BAND);
  const { data: summary } = useDashboardSummary();

  const leads = useMemo(() => {
    return (region ? allLeads.filter((s) => s.properties.region === region) : allLeads).slice(0, MAX_LEADS);
  }, [allLeads, region]);

  const incidents = useMemo(() => {
    return [...(summary?.recent_incidents ?? [])]
      .filter((i) => inWindow(i.timestamp, timeWindow))
      .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  }, [summary, timeWindow]);

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <span className={styles.title}>ELEVATED LEADS</span>
        <span className={styles.meta}>
          {leads.length}
          {region ? ` in ${region}` : " ranked"}
        </span>
      </div>

      <div className={styles.leadsScroll}>
        {leads.map((s, i) => (
          <button
            key={s.id}
            type="button"
            className={styles.leadRow}
            data-selected={selectedId === s.id}
            onClick={() => select(s.id)}
          >
            <span className={styles.rank}>{String(i + 1).padStart(2, "0")}</span>
            <EntityTypeIcon label={s.label} size={14} />
            <span>
              <span className={styles.leadName}>{s.name}</span>
              <span className={styles.leadPlace}>
                {[s.properties.city, s.properties.country].filter(Boolean).join(", ")} · {s.properties.region}
              </span>
            </span>
            <span className={styles.leadScoreGroup}>
              <span className={styles.leadScore} style={{ color: bandColorVar(s.assessment?.band) }}>
                {s.assessment?.score ?? "—"}
              </span>
            </span>
          </button>
        ))}
        {leads.length === 0 ? (
          <p className={styles.emptyLeads}>No elevated subject matches the current working set. Clear the window or the region to widen it.</p>
        ) : null}
      </div>

      <div className={styles.incidentsBlock}>
        <div className={styles.head}>
          <span className={styles.title}>INCIDENTS</span>
          <span className={styles.meta}>{incidents.length} shown</span>
        </div>
        <div className={styles.incidentsScroll}>
          {incidents.map((i) => (
            <div key={i.incident_id} className={styles.incidentRow}>
              <span className={styles.incidentHead}>
                <span className={styles.incidentDot} style={{ background: severityColorVar(i.severity) }} />
                <span className={styles.incidentType}>{i.type}</span>
                <span className={styles.incidentAgo}>{formatAgo(i.timestamp)} ago</span>
              </span>
              <span className={styles.incidentRule}>{i.description}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
