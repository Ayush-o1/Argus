"use client";

import { Clock } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageShell } from "@/components/layout/PageShell";
import { ActivityHistogram } from "@/components/timeline/ActivityHistogram";
import { NotableMoments } from "@/components/timeline/NotableMoments";
import { TimelineChart } from "@/components/timeline/TimelineChart";
import {
  analyseDays,
  DEFAULT_FILTERS,
  filterDetail,
  LANE_LABEL,
  LANES,
  type LaneKey,
  type TimelineFilters,
} from "@/components/timeline/timelineModel";
import { useGlobalTimeline } from "@/hooks/useTimeline";
import { useTemporalPatterns } from "@/hooks/usePatterns";
import { coverageLabel } from "@/lib/aggregate";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";
import styles from "./page.module.css";

const RANGE_OPTIONS = [
  { value: "7", label: "7d" },
  { value: "30", label: "30d" },
  { value: "90", label: "90d" },
  { value: "all", label: "All" },
];

const LEGEND = [
  { label: "Flagged activity", color: RISK_COLORS.Critical },
  { label: "Baseline transactions", color: ENTITY_COLORS.Account },
  { label: "Baseline communications", color: ENTITY_COLORS.Device },
  { label: "Events", color: ENTITY_COLORS.Event },
];

export default function TimelinePage() {
  const { data, isLoading, isError, refetch } = useGlobalTimeline();
  const [filters, setFilters] = useState<TimelineFilters>(DEFAULT_FILTERS);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const { data: temporal } = useTemporalPatterns();

  // Which days the *server* found unusual, by a two-sided Poisson test of each
  // day against the rate implied by every other day. Computed there because the
  // test needs the whole series and a baseline excluding the day under test —
  // neither of which survives the user toggling a lane in the browser.
  const unusualDays = useMemo(() => {
    const map = new Map<string, "high" | "low">();
    for (const series of temporal?.series ?? []) {
      for (const day of series.daily) {
        if (day.unusual && day.unusual_direction) map.set(day.day, day.unusual_direction);
      }
    }
    return map;
  }, [temporal]);

  const analysis = useMemo(
    () => (data ? analyseDays(data, filters, unusualDays) : null),
    [data, filters, unusualDays],
  );
  const detail = useMemo(() => (data ? filterDetail(data, filters) : null), [data, filters]);

  const reportedTotal = analysis?.days.reduce((sum, d) => sum + d.sourceReported, 0) ?? 0;
  const dayCount = analysis?.days.length ?? 0;
  const unusualCount = analysis?.days.filter((d) => d.unusual).length ?? 0;

  function setLane(lane: LaneKey, on: boolean) {
    setFilters((f) => ({ ...f, lanes: { ...f.lanes, [lane]: on } }));
    setSelectedDay(null);
  }

  const isEmpty =
    detail &&
    detail.transactions.length === 0 &&
    detail.communications.length === 0 &&
    detail.events.length === 0 &&
    detail.incidents.length === 0;

  // The scatter renders a bounded preview per lane, while every figure above it
  // is a complete count. Saying so prevents the reader inferring the chart is
  // the whole picture.
  const previewNote = data
    ? [
        coverageLabel(data.detail.transactions.coverage) && "transactions",
        coverageLabel(data.detail.communications.coverage) && "communications",
        coverageLabel(data.detail.events.coverage) && "events",
      ].filter(Boolean)
    : [];

  return (
    <PageShell
      title="Timeline"
      subtitle={
        analysis
          ? `${reportedTotal.toLocaleString()} source-reported record${
              reportedTotal === 1 ? "" : "s"
            } across ${dayCount} day${dayCount === 1 ? "" : "s"}${
              unusualCount > 0 ? ` · ${unusualCount} day${unusualCount === 1 ? "" : "s"} tested unusual` : ""
            } — select a day to narrow the sequence`
          : "Reconstruct what happened, and when"
      }
    >
      {isError ? (
        <EmptyState
          icon={Clock}
          title="Could not load the timeline"
          description="The activity data could not be retrieved. This is a loading failure, not an empty result — the graph may still contain activity."
          actions={
            <Button variant="secondary" size="sm" onClick={() => void refetch()}>
              Retry
            </Button>
          }
        />
      ) : isLoading || !data || !analysis || !detail ? (
        <Skeleton height={520} />
      ) : (
        <div className={styles.layout}>
          <div className={styles.main}>
            <Card>
              <div className={styles.toolbar}>
                <SegmentedControl
                  segments={RANGE_OPTIONS}
                  value={filters.rangeDays === null ? "all" : String(filters.rangeDays)}
                  onChange={(v) => {
                    setFilters((f) => ({ ...f, rangeDays: v === "all" ? null : Number(v) }));
                    setSelectedDay(null);
                  }}
                  ariaLabel="Time range"
                />
                <div className={styles.lanes}>
                  {LANES.map((lane) => (
                    <Checkbox
                      key={lane}
                      checked={filters.lanes[lane]}
                      onChange={(e) => setLane(lane, e.target.checked)}
                      label={LANE_LABEL[lane]}
                    />
                  ))}
                </div>
                <div className={styles.spacer} />
                <Checkbox
                  checked={filters.sourceReportedOnly}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, sourceReportedOnly: e.target.checked }));
                    setSelectedDay(null);
                  }}
                  label="Flagged only"
                />
              </div>

              <div className={styles.histogramHead}>
                <span className={styles.sectionTitle}>Daily volume</span>
                {/* States the basis of the claim, not just the claim. A reader
                    can check the threshold against the bars rather than taking
                    "2σ" on trust. */}
                <span
                  className={styles.sectionHint}
                  title={`Counted across all ${data.totals.records.population?.toLocaleString() ?? "—"} records in the graph`}
                >
                  {/* Was "N days above 2σ", computed in the browser over the
                      filtered range with a threshold the bursts themselves
                      inflated. This is the server's per-day Poisson test,
                      corrected across the series. */}
                  {!temporal
                    ? "Testing days against the rest of the series…"
                    : unusualCount > 0
                      ? `${unusualCount} day${unusualCount === 1 ? "" : "s"} depart from the rest of the series (Poisson test against a leave-one-out baseline, corrected)`
                      : "No day departs significantly from the rest of the series"}
                </span>
              </div>
              <ActivityHistogram days={analysis.days} selectedDay={selectedDay} onSelectDay={setSelectedDay} />
            </Card>

            <Card>
              <div className={styles.histogramHead}>
                <span className={styles.sectionTitle}>Activity by type</span>
                <div className={styles.legend}>
                  {LEGEND.map((item) => (
                    <span key={item.label} className={styles.legendItem}>
                      <span className={styles.dot} style={{ background: item.color }} />
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
              {previewNote.length > 0 ? (
                <p className={styles.previewNote}>
                  Showing the most recent records for {previewNote.join(", ")}; the volume chart above
                  counts every record.
                </p>
              ) : null}
              {isEmpty ? (
                <EmptyState
                  icon={Clock}
                  title="Nothing in this selection"
                  description="Widen the time range or re-enable an activity type."
                />
              ) : (
                <TimelineChart data={detail} />
              )}
            </Card>
          </div>

          <NotableMoments data={detail} selectedDay={selectedDay} />
        </div>
      )}
    </PageShell>
  );
}
