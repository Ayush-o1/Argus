"use client";

import Link from "next/link";
import { formatScore } from "@/lib/assessment";
import { Globe2, ShieldHalf } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/Badge";
import { formatRelativeTime } from "@/lib/formatters";
import { entityId } from "@/lib/entityDisplay";
import { PRIORITY_TONE, RULE_LABEL, formatPriority, type Alert } from "@/lib/alerts";
import styles from "./CaseFootprint.module.css";

/**
 * What the case actually spans, and what already fired against it.
 *
 * A case previously showed an evidence board and nothing else, so two
 * questions an investigator asks immediately — how far does this reach, and
 * what triggered it — had no answer on the page. Both are derived from data
 * already loaded: the linked entities carry their own geography, and alerts
 * carry the entity IDs they involve.
 */

interface LinkedEntity {
  label: string;
  properties: Record<string, unknown>;
}

export function CaseFootprint({
  entities,
  alerts,
  caseId,
}: {
  entities: LinkedEntity[];
  alerts: Alert[] | undefined;
  caseId: string;
}) {
  const model = useMemo(() => {
    const countries = new Set<string>();
    const regions = new Set<string>();
    const byLabel = new Map<string, number>();
    // Null until an assessed entity is seen, so "no assessed entity on this
    // board" cannot render as a peak of 0 — which would read as a case full of
    // cleared entities rather than one ARGUS has no view on.
    let peakScore: number | null = null;

    for (const e of entities) {
      const p = e.properties;
      if (typeof p.country === "string") countries.add(p.country);
      if (typeof p.region === "string") regions.add(p.region);
      if (typeof p.argus_score === "number") {
        peakScore = peakScore === null ? p.argus_score : Math.max(peakScore, p.argus_score);
      }
      byLabel.set(e.label, (byLabel.get(e.label) ?? 0) + 1);
    }

    // An alert belongs to this case when one of its subjects is on the evidence
    // board. `scope` is the alert's full subject list rather than a preview, so
    // this match cannot miss an entity the alert covers but did not display.
    const linkedIds = new Set(entities.map((e) => entityId(e.label, e.properties)).filter(Boolean) as string[]);
    const related = (alerts ?? []).filter((a) => a.scope.some((ref) => linkedIds.has(ref)));

    return {
      countries: [...countries],
      regions: [...regions],
      composition: [...byLabel.entries()].sort((a, b) => b[1] - a[1]),
      peakScore,
      related,
    };
  }, [entities, alerts]);

  const { countries, regions, composition, peakScore, related } = model;

  return (
    <div className={styles.wrap}>
      <section className={styles.block}>
        <h3 className={styles.blockTitle}>Footprint</h3>
        {entities.length === 0 ? (
          <p className={styles.muted}>Link entities to the evidence board to establish a footprint.</p>
        ) : (
          <>
            <div className={styles.stats}>
              <Stat label="Entities" value={entities.length} />
              <Stat label="Countries" value={countries.length || "—"} />
              <Stat label="Regions" value={regions.length || "—"} />
              <Stat
                label="Peak assessment"
                value={formatScore(peakScore) ?? "—"}
                tone={(peakScore ?? 0) >= 60}
              />
            </div>

            {countries.length > 0 ? (
              <p className={styles.places}>
                <Globe2 size={13} /> {countries.join(", ")}
                {regions.length > 1 ? (
                  <span className={styles.crossRegion}>Crosses {regions.length} regions</span>
                ) : null}
              </p>
            ) : null}

            <div className={styles.composition}>
              {composition.map(([label, count]) => (
                <span key={label} className={styles.chip}>
                  {label}
                  <span className={styles.chipCount}>{count}</span>
                </span>
              ))}
            </div>
          </>
        )}
      </section>

      <section className={styles.block}>
        <h3 className={styles.blockTitle}>Related alerts {related.length > 0 ? `(${related.length})` : ""}</h3>
        {related.length === 0 ? (
          <p className={styles.muted}>No alert currently involves an entity on this case&rsquo;s evidence board.</p>
        ) : (
          <ul className={styles.alerts}>
            {related.map((alert) => (
              <li key={alert.alert_key}>
                <Link href={`/alerts?focus=${alert.alert_key}`} className={styles.alertRow}>
                  <ShieldHalf size={13} />
                  <span className={styles.alertBody}>
                    <span className={styles.alertTitle}>
                      {RULE_LABEL[alert.rule_id] ?? alert.rule_id}
                    </span>
                    <span className={styles.alertDesc}>{alert.summary}</span>
                  </span>
                  <Badge tone={PRIORITY_TONE[alert.priority_band]}>
                    {formatPriority(alert.priority)}
                  </Badge>
                  <span className={styles.alertTime}>{formatRelativeTime(alert.last_seen_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {entities.length > 0 ? (
        <Link href={`/graph?seed=${entityId(entities[0].label, entities[0].properties) ?? caseId}`} className={styles.graphLink}>
          Open the evidence board in the Graph Explorer →
        </Link>
      ) : null}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: boolean }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={tone ? styles.statValueHot : styles.statValue}>{value}</span>
    </div>
  );
}
