"use client";

import { useMemo } from "react";
import type { DashboardSummary } from "@/lib/types";
import type { RegionRollup } from "@/hooks/useMap";
import styles from "./SituationBrief.module.css";

/**
 * Bottom line up front.
 *
 * A strip of standalone counters ("Open alerts: 9") reports data and leaves the
 * analyst to assemble the meaning. An intelligence product states the position
 * first, in a sentence, and keeps the figures as support. The prose here is
 * composed only from values actually present in the dataset — nothing is
 * asserted that the summary and region rollup don't contain.
 */

interface SituationBriefProps {
  summary: DashboardSummary;
  regions: RegionRollup[] | undefined;
}

export function SituationBrief({ summary, regions }: SituationBriefProps) {
  const model = useMemo(() => {
    const critical = summary.risk_distribution.find((b) => b.level === "Critical")?.count ?? 0;
    const high = summary.risk_distribution.find((b) => b.level === "High")?.count ?? 0;
    const elevated = critical + high;

    const active = (regions ?? []).filter((r) => r.elevated_count > 0);
    const ranked = [...active].sort((a, b) => b.elevated_count - a.elevated_count);
    const lead = ranked[0];
    const anomalyLead = [...(regions ?? [])].sort((a, b) => b.anomalous_routes - a.anomalous_routes)[0];

    // A leader by a single entity is not a concentration. Stating "concentrated
    // in X" for a one-entity margin reads as a finding when it is noise, so the
    // claim is only made when the margin is material.
    const runnerUp = ranked[1];
    const isConcentrated =
      lead !== undefined &&
      (runnerUp === undefined || lead.elevated_count >= runnerUp.elevated_count * 1.5) &&
      lead.elevated_count > 1;

    return { critical, high, elevated, active, lead, runnerUp, isConcentrated, anomalyLead };
  }, [summary, regions]);

  const { critical, elevated, active, lead, isConcentrated, anomalyLead } = model;

  return (
    <section className={styles.brief} aria-label="Situation">
      <p className={styles.statement}>
        {elevated > 0 ? (
          <>
            <strong>{elevated}</strong> {elevated === 1 ? "entity is" : "entities are"} carrying elevated risk
            {active.length > 0 ? (
              <>
                {" "}
                across <strong>{active.length}</strong> {active.length === 1 ? "region" : "regions"}
              </>
            ) : null}
            {lead && isConcentrated ? (
              <>
                , concentrated in <strong>{lead.region}</strong>
              </>
            ) : lead ? (
              <>
                , led by <strong>{lead.region}</strong>
              </>
            ) : null}
            .
          </>
        ) : (
          <>No entity currently exceeds the elevated-risk threshold.</>
        )}{" "}
        {/* Both figures are full-population counts, so they can be stated as
            parts of one whole. The critical count previously came from a
            six-row display list and understated itself (audit B-05). */}
        <strong>{summary.open_alerts}</strong> {summary.open_alerts === 1 ? "alert is" : "alerts are"} open
        {summary.critical_open_alerts > 0 ? (
          <>
            , <strong>{summary.critical_open_alerts}</strong> of them critical
          </>
        ) : null}
        .
        {anomalyLead && anomalyLead.anomalous_routes > 0 ? (
          <>
            {" "}
            Route anomalies cluster on <strong>{anomalyLead.region}</strong> (
            {anomalyLead.anomalous_routes} flagged).
          </>
        ) : null}
      </p>

      <dl className={styles.figures}>
        <Figure label="Critical entities" value={critical} tone={critical > 0 ? "critical" : undefined} />
        <Figure
          label={`Incidents · ${summary.window_days}d`}
          value={summary.incidents_in_window}
          tone={summary.incidents_in_window > 0 ? "high" : undefined}
        />
        <Figure label="Open alerts" value={summary.open_alerts} />
        <Figure label="Active cases" value={summary.active_cases} />
        <Figure label="Mean risk" value={summary.avg_risk_score.toFixed(1)} suffix="/100" />
      </dl>
    </section>
  );
}

function Figure({
  label,
  value,
  suffix,
  tone,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  tone?: "critical" | "high";
}) {
  return (
    <div className={styles.figure}>
      <dt className={styles.figureLabel}>{label}</dt>
      <dd className={styles.figureValue}>
        <span className={tone ? styles[tone] : undefined}>{value}</span>
        {suffix ? <span className={styles.figureSuffix}>{suffix}</span> : null}
      </dd>
    </div>
  );
}
