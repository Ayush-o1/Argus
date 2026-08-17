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
    const elevated = summary.elevated_entities;
    const unassessable =
      (summary.assessment_distribution.find((b) => b.band === "insufficient_evidence")?.count ?? 0) +
      (summary.assessment_distribution.find((b) => b.band === "unassessed")?.count ?? 0);

    const active = (regions ?? []).filter((r) => r.elevated_count > 0);
    const ranked = [...active].sort((a, b) => b.elevated_count - a.elevated_count);
    const lead = ranked[0];
    const anomalyLead = [...(regions ?? [])].sort((a, b) => b.flagged_routes - a.flagged_routes)[0];

    // A leader by a single entity is not a concentration. Stating "concentrated
    // in X" for a one-entity margin reads as a finding when it is noise, so the
    // claim is only made when the margin is material.
    const runnerUp = ranked[1];
    const isConcentrated =
      lead !== undefined &&
      (runnerUp === undefined || lead.elevated_count >= runnerUp.elevated_count * 1.5) &&
      lead.elevated_count > 1;

    return { elevated, unassessable, active, lead, runnerUp, isConcentrated, anomalyLead };
  }, [summary, regions]);

  const { elevated, unassessable, active, lead, isConcentrated, anomalyLead } = model;

  return (
    <section className={styles.brief} aria-label="Situation">
      <p className={styles.statement}>
        {elevated > 0 ? (
          <>
            {/* "ARGUS assessed" rather than "carrying elevated risk". The
                second phrasing makes the band sound like a property of the
                person; it is a statement about what the evidence supports, and
                the sentence has to say whose judgement it is. */}
            ARGUS assessed <strong>{elevated}</strong>{" "}
            {elevated === 1 ? "entity" : "entities"} as warranting review
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
          <>
            ARGUS assessed no entity as warranting review
            {unassessable > 0 ? (
              <>
                , and could not assess <strong>{unassessable.toLocaleString()}</strong>
              </>
            ) : null}
            .
          </>
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
        {anomalyLead && anomalyLead.flagged_routes > 0 ? (
          <>
            {" "}
            Flagged routes cluster on <strong>{anomalyLead.region}</strong> (
            {anomalyLead.flagged_routes} of them).
          </>
        ) : null}
      </p>

      <dl className={styles.figures}>
        <Figure label="Elevated entities" value={elevated} tone={elevated > 0 ? "critical" : undefined} />
        <Figure
          label={`Incidents · ${summary.window_days}d`}
          value={summary.incidents_in_window}
          tone={summary.incidents_in_window > 0 ? "high" : undefined}
        />
        <Figure label="Open alerts" value={summary.open_alerts} />
        <Figure label="Active cases" value={summary.active_cases} />
        {/* Replaces "Mean risk". An average over a population ARGUS mostly
            could not assess summarises nothing; the number of subjects it had
            no view on is the figure that actually qualifies the rest. */}
        <Figure label="Not assessable" value={unassessable} />
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
