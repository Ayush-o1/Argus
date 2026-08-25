"use client";

import { useMemo, useState } from "react";
import { ActivityHistogram } from "@/components/timeline/ActivityHistogram";
import { analyseDays, DEFAULT_FILTERS } from "@/components/timeline/timelineModel";
import { nextFixtureGlobalTimeline, nextFixtureUnusualDays } from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./InvestigateWorkspace.module.css";

/**
 * The Timeline lens — the real `ActivityHistogram` (@visx) driven by fixture
 * day buckets, same reuse pattern as Graph/Map. `analyseDays` is the exact
 * function the real `/timeline` page uses to turn buckets into the shape the
 * chart expects, run here against `nextFixtureGlobalTimeline` instead of a
 * live `useGlobalTimeline()` query.
 *
 * A drag-to-zoom selection writes straight into the shared scope bus's
 * `timeWindow` — `nextScopeStore`'s own docstring calls this out as the
 * reason it mirrors `TimelineFilters.zoomRange`'s shape exactly. Lane
 * filters, source-reported-only, and the record-level "what happened that
 * day" panel (`NotableMoments`, which needs per-record fixture data not yet
 * built) aren't wired in this pass.
 */
export function TimelineLens() {
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const setTimeWindow = useNextScopeStore((s) => s.setTimeWindow);

  const filters = useMemo(
    () => ({ ...DEFAULT_FILTERS, zoomRange: timeWindow }),
    [timeWindow],
  );

  const analysis = useMemo(
    () => analyseDays(nextFixtureGlobalTimeline, filters, nextFixtureUnusualDays),
    [filters],
  );

  const selected = selectedDay ? analysis.days.find((d) => d.day === selectedDay) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", padding: "18px", height: "100%", overflowY: "auto" }}>
      <ActivityHistogram
        days={analysis.days}
        selectedDay={selectedDay}
        onSelectDay={setSelectedDay}
        onZoom={(range) => setTimeWindow(range)}
      />
      {timeWindow ? (
        <button
          type="button"
          className={styles.isolateExit}
          style={{ position: "static", alignSelf: "flex-start", marginTop: "12px" }}
          onClick={() => setTimeWindow(null)}
        >
          CLEAR TIME WINDOW
        </button>
      ) : null}
      {selected ? (
        <div className={styles.selectedStrip} style={{ borderTop: 0, marginTop: "12px", padding: 0 }}>
          <span className={styles.selectedName}>{selected.day}</span>
          <span className={styles.selectedMeta}>
            {selected.total} records{selected.unusual ? ` · ${selected.unusualDirection?.toUpperCase()} vs baseline` : ""}
          </span>
        </div>
      ) : null}
    </div>
  );
}
