"use client";

import { useMemo, useState } from "react";
import { ActivityHistogram } from "@/components/timeline/ActivityHistogram";
import { NotableMoments } from "@/components/timeline/NotableMoments";
import { analyseDays, DEFAULT_FILTERS, filterDetail, LANE_LABEL, LANES, type LaneKey } from "@/components/timeline/timelineModel";
import { Checkbox } from "@/components/ui/Checkbox";
import { Skeleton } from "@/components/ui/Skeleton";
import { useGlobalTimeline } from "@/hooks/useTimeline";
import { useTemporalPatterns } from "@/hooks/usePatterns";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./InvestigateWorkspace.module.css";

/**
 * The Timeline lens — the real `ActivityHistogram` (@visx) and `NotableMoments`
 * panel, same reuse pattern as Graph/Map. `analyseDays`/`filterDetail` are the
 * exact functions the real `/timeline` page uses to turn buckets into what
 * the chart and moments list expect — `filterDetail` derives its result from
 * the same `useGlobalTimeline` payload this lens already holds, so lane and
 * flagged-only filtering costs no extra request.
 *
 * Live-wired (Phase 12): `useGlobalTimeline`/`useTemporalPatterns` and the
 * `unusualDays` derivation are identical to `GlobalActivity`'s (Command
 * mode) — same query keys, so switching to this lens after visiting Command
 * reads from cache rather than refetching.
 *
 * A drag-to-zoom selection writes straight into the shared scope bus's
 * `timeWindow` — `nextScopeStore`'s own docstring calls this out as the
 * reason it mirrors `TimelineFilters.zoomRange`'s shape exactly. Lane
 * filters and source-reported-only are local state here rather than routed
 * through the store: they scope what this lens renders, not the shared
 * working-set context the way region/time window do. `NotableMoments`'
 * incident rows link out to the old app's `/alerts?focus=`, unchanged from
 * how the real `/timeline` page uses it — a real, working destination, not
 * a component built around a route this experience has replaced.
 */
export function TimelineLens() {
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [lanes, setLanes] = useState(DEFAULT_FILTERS.lanes);
  const [sourceReportedOnly, setSourceReportedOnly] = useState(false);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const setTimeWindow = useNextScopeStore((s) => s.setTimeWindow);

  const { data: timeline, isLoading: timelineLoading } = useGlobalTimeline();
  const { data: temporal } = useTemporalPatterns();

  const unusualDays = useMemo(() => {
    const map = new Map<string, "high" | "low">();
    for (const series of temporal?.series ?? []) {
      for (const day of series.daily) {
        if (day.unusual && day.unusual_direction) map.set(day.day, day.unusual_direction);
      }
    }
    return map;
  }, [temporal]);

  const filters = useMemo(
    () => ({ ...DEFAULT_FILTERS, lanes, sourceReportedOnly, zoomRange: timeWindow }),
    [lanes, sourceReportedOnly, timeWindow],
  );

  const analysis = useMemo(
    () => (timeline ? analyseDays(timeline, filters, unusualDays) : null),
    [timeline, filters, unusualDays],
  );
  const detail = useMemo(() => (timeline ? filterDetail(timeline, filters) : null), [timeline, filters]);

  const selected = analysis && selectedDay ? analysis.days.find((d) => d.day === selectedDay) : null;

  function setLane(lane: LaneKey, on: boolean) {
    setLanes((l) => ({ ...l, [lane]: on }));
    setSelectedDay(null);
  }

  if (timelineLoading || !analysis || !detail) {
    return <Skeleton height={220} />;
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      <div style={{ display: "flex", flexDirection: "column", padding: "18px", flex: 1, minWidth: 0, overflowY: "auto" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "14px", alignItems: "center", marginBottom: "10px" }}>
          {LANES.map((lane) => (
            <Checkbox key={lane} checked={lanes[lane]} onChange={(e) => setLane(lane, e.target.checked)} label={LANE_LABEL[lane]} />
          ))}
          <Checkbox
            checked={sourceReportedOnly}
            onChange={(e) => {
              setSourceReportedOnly(e.target.checked);
              setSelectedDay(null);
            }}
            label="Flagged only"
          />
        </div>
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
      <div style={{ width: "320px", flexShrink: 0, borderLeft: "1px solid var(--surface-border-faint)", overflowY: "auto" }}>
        <NotableMoments data={detail} selectedDay={selectedDay} />
      </div>
    </div>
  );
}
