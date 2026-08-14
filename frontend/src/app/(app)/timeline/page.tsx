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
  BURST_SIGMA,
  DEFAULT_FILTERS,
  filterDetail,
  LANE_LABEL,
  LANES,
  type LaneKey,
  type TimelineFilters,
} from "@/components/timeline/timelineModel";
import { useGlobalTimeline } from "@/hooks/useTimeline";
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

  const analysis = useMemo(() => (data ? analyseDays(data, filters) : null), [data, filters]);
  const detail = useMemo(() => (data ? filterDetail(data, filters) : null), [data, filters]);

  const flaggedTotal = analysis?.days.reduce((sum, d) => sum + d.flagged, 0) ?? 0;

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
          ? `${flaggedTotal.toLocaleString()} flagged record${flaggedTotal === 1 ? "" : "s"} across ${
              analysis.stats.dayCount
            } day${analysis.stats.dayCount === 1 ? "" : "s"}${
              analysis.stats.burstDays > 0
                ? ` · ${analysis.stats.burstDays} burst day${analysis.stats.burstDays === 1 ? "" : "s"}`
                : ""
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
                  checked={filters.flaggedOnly}
                  onChange={(e) => {
                    setFilters((f) => ({ ...f, flaggedOnly: e.target.checked }));
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
                  {analysis.stats.sigma === 0
                    ? "No variation in flagged volume across this range"
                    : analysis.stats.burstDays > 0
                      ? `${analysis.stats.burstDays} day${analysis.stats.burstDays === 1 ? "" : "s"} above ${BURST_SIGMA}σ (>${analysis.stats.threshold.toFixed(1)} flagged/day vs mean ${analysis.stats.mean.toFixed(1)})`
                      : `No day exceeds ${BURST_SIGMA}σ (>${analysis.stats.threshold.toFixed(1)} flagged/day vs mean ${analysis.stats.mean.toFixed(1)})`}
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
                  Showing the most recent and flagged records for {previewNote.join(", ")}; the volume chart above
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
