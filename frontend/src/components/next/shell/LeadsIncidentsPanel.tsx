"use client";

import { useMemo } from "react";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { nextFixtureAnalystJudgements, nextFixtureIncidents, nextFixtureSubjects } from "@/lib/next/fixtures";
import { DIVERGENCE_THRESHOLD, bandColorVar, formatAgo, severityColorVar } from "@/lib/next/format";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./LeadsIncidentsPanel.module.css";

const LEAD_LABELS = new Set(["Person", "Organization"]);
const MAX_LEADS = 25;

function inWindow(iso: string, window: { start: number; end: number } | null): boolean {
  if (!window) return true;
  const t = Date.parse(iso);
  return t >= Math.min(window.start, window.end) && t <= Math.max(window.start, window.end);
}

/**
 * Elevated leads + recent incidents — the same panel content whether it's
 * docked (desktop) or a slide-over sheet (compact layout). Reads the scope
 * bus for region/time-window so this list narrows exactly in step with
 * everything else, matching Phase 4's "one source of truth" requirement.
 */
export function LeadsIncidentsPanel() {
  const region = useNextScopeStore((s) => s.region);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);

  const leads = useMemo(() => {
    return nextFixtureSubjects
      .filter((s) => LEAD_LABELS.has(s.label) && s.assessment?.band === "elevated")
      .filter((s) => !region || s.properties.region === region)
      .sort((a, b) => (b.assessment?.score ?? 0) - (a.assessment?.score ?? 0))
      .slice(0, MAX_LEADS);
  }, [region]);

  const incidents = useMemo(() => {
    return nextFixtureIncidents
      .filter((i) => inWindow(i.timestamp, timeWindow))
      .filter((i) => {
        if (!region) return true;
        const subjectId = i.involved_entity_ids?.[0];
        const subject = subjectId ? nextFixtureSubjects.find((s) => s.id === subjectId) : null;
        return subject?.properties.region === region;
      })
      .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  }, [region, timeWindow]);

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
        {leads.map((s, i) => {
          const analyst = nextFixtureAnalystJudgements[s.id];
          const divergence = analyst && s.assessment?.score !== null ? Math.abs((s.assessment?.score ?? 0) - analyst.score) : 0;
          const diverges = !!analyst && divergence >= DIVERGENCE_THRESHOLD;
          return (
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
                {diverges ? <span className={styles.divergeMark} title={`Analyst differs by ${divergence} points`} /> : null}
                <span className={styles.leadScore} style={{ color: bandColorVar(s.assessment?.band) }}>
                  {s.assessment?.score ?? "—"}
                </span>
              </span>
            </button>
          );
        })}
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
          {incidents.map((i) => {
            const subjectId = i.involved_entity_ids?.[0];
            const subject = subjectId ? nextFixtureSubjects.find((s) => s.id === subjectId) : null;
            return (
              <button key={i.incident_id} type="button" className={styles.incidentRow} onClick={() => subjectId && select(subjectId)}>
                <span className={styles.incidentHead}>
                  <span className={styles.incidentDot} style={{ background: severityColorVar(i.severity) }} />
                  <span className={styles.incidentType}>{i.type}</span>
                  <span className={styles.incidentAgo}>{formatAgo(i.timestamp)} ago</span>
                </span>
                {subject ? <span className={styles.incidentSubject}>{subject.name}</span> : null}
                <span className={styles.incidentRule}>{i.description}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
