"use client";

import { useMemo, useState } from "react";
import { ActivityHistogram } from "@/components/timeline/ActivityHistogram";
import { analyseDays, DEFAULT_FILTERS } from "@/components/timeline/timelineModel";
import { nextFixtureActivityDays, nextFixtureRegions, nextFixtureUnusualDays } from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./GlobalActivity.module.css";
import type { GlobalTimeline } from "@/hooks/useTimeline";

/**
 * Global daily volume + region breakdown.
 *
 * Reuses the real `ActivityHistogram` and `analyseDays` (the Poisson-tested
 * burst detection already shipping on `/timeline`) rather than a second
 * histogram implementation — the same drag-to-window gesture from that page
 * now writes into the shared scope bus instead of page-local state, which is
 * exactly what Phase 4's "one source of truth" means in practice.
 */
export function GlobalActivity() {
  const region = useNextScopeStore((s) => s.region);
  const setRegion = useNextScopeStore((s) => s.setRegion);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const setTimeWindow = useNextScopeStore((s) => s.setTimeWindow);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const analysis = useMemo(
    () => analyseDays({ buckets: nextFixtureActivityDays } as GlobalTimeline, DEFAULT_FILTERS, nextFixtureUnusualDays),
    [],
  );
  const unusualCount = analysis.days.filter((d) => d.unusual).length;

  const maxEntities = Math.max(...nextFixtureRegions.map((r) => r.entity_count));

  return (
    <section className={styles.section} aria-label="Global activity">
      <div className={styles.head}>
        <span className={styles.label}>GLOBAL ACTIVITY</span>
        <span className={styles.rule} />
        <span className={styles.meta}>FLAGGED EVENTS · 90D · POISSON TEST, CORRECTED</span>
      </div>

      <ActivityHistogram
        days={analysis.days}
        selectedDay={selectedDay}
        onSelectDay={setSelectedDay}
        onZoom={(range) => setTimeWindow(range)}
      />
      <p className={styles.hint}>
        {unusualCount > 0
          ? `${unusualCount} day${unusualCount === 1 ? "" : "s"} depart from the rest of the series`
          : "No day departs significantly from the rest of the series"}
        {" · drag across the chart to set a window — every lens follows it"}
        {timeWindow ? (
          <>
            {" · "}
            <button type="button" className={styles.resetWindow} onClick={() => setTimeWindow(null)}>
              reset window
            </button>
          </>
        ) : null}
      </p>

      <div className={styles.regionGrid} role="group" aria-label="Filter by region">
        {nextFixtureRegions.map((r) => {
          const active = region === r.region;
          const accent = r.elevated_count >= 4 ? "var(--risk-critical)" : r.elevated_count >= 1 ? "var(--risk-high)" : "var(--surface-border)";
          return (
            <button
              key={r.region}
              type="button"
              className={styles.regionCell}
              data-active={active}
              title={`${r.region} — ${r.entity_count.toLocaleString("en-US")} entities, ${r.elevated_count} elevated, ${r.flagged_routes} flagged routes`}
              onClick={() => setRegion(active ? null : r.region)}
            >
              <span className={styles.regionName}>{r.region}</span>
              <span className={styles.regionFigures}>
                <span className={styles.regionCount} style={{ color: accent }}>
                  {r.elevated_count > 0 ? r.elevated_count : "—"}
                </span>
                <span className={styles.regionRoutes}>{r.flagged_routes > 0 ? `${r.flagged_routes} routes` : "no routes"}</span>
              </span>
              <span className={styles.regionBarTrack}>
                <span
                  className={styles.regionBarFill}
                  style={{ width: `${Math.max(4, Math.round((r.entity_count / maxEntities) * 100))}%`, background: accent }}
                />
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
