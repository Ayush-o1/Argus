"use client";

import { Clock } from "lucide-react";
import { useMemo, useState } from "react";
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
  applyFilters,
  bucketByDay,
  DEFAULT_FILTERS,
  LANE_LABEL,
  type LaneKey,
  type TimelineFilters,
} from "@/components/timeline/timelineModel";
import { useGlobalTimeline } from "@/hooks/useTimeline";
import { ENTITY_COLORS, RISK_COLORS } from "@/lib/theme";
import styles from "./page.module.css";

const RANGE_OPTIONS = [
  { value: "7", label: "7d" },
  { value: "30", label: "30d" },
  { value: "90", label: "90d" },
  { value: "all", label: "All" },
];

const LANES: LaneKey[] = ["incidents", "transactions", "communications", "events"];

const LEGEND = [
  { label: "Flagged activity", color: RISK_COLORS.Critical },
  { label: "Baseline transactions", color: ENTITY_COLORS.Account },
  { label: "Baseline communications", color: ENTITY_COLORS.Device },
  { label: "Events", color: ENTITY_COLORS.Event },
];

export default function TimelinePage() {
  const { data, isLoading } = useGlobalTimeline();
  const [filters, setFilters] = useState<TimelineFilters>(DEFAULT_FILTERS);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const buckets = useMemo(() => (data ? bucketByDay(data, filters) : []), [data, filters]);
  const filtered = useMemo(() => (data ? applyFilters(data, filters) : null), [data, filters]);

  const burstDays = buckets.filter((b) => b.burst).length;
  const flaggedTotal = buckets.reduce((sum, b) => sum + b.flagged, 0);

  function setLane(lane: LaneKey, on: boolean) {
    setFilters((f) => ({ ...f, lanes: { ...f.lanes, [lane]: on } }));
    setSelectedDay(null);
  }

  const isEmpty =
    filtered &&
    filtered.transactions.length === 0 &&
    filtered.communications.length === 0 &&
    filtered.events.length === 0 &&
    filtered.incidents.length === 0;

  return (
    <PageShell
      title="Timeline"
      subtitle={
        data
          ? `${flaggedTotal.toLocaleString()} flagged record${flaggedTotal === 1 ? "" : "s"}${
              burstDays > 0 ? ` across ${burstDays} burst day${burstDays === 1 ? "" : "s"}` : ""
            } — select a day to narrow the sequence`
          : "Reconstruct what happened, and when"
      }
    >
      {isLoading || !data || !filtered ? (
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
                <span className={styles.sectionHint}>
                  {burstDays > 0
                    ? `${burstDays} day${burstDays === 1 ? "" : "s"} above 2σ of flagged volume`
                    : "No days exceed 2σ of flagged volume"}
                </span>
              </div>
              <ActivityHistogram buckets={buckets} selectedDay={selectedDay} onSelectDay={setSelectedDay} />
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
              {isEmpty ? (
                <EmptyState
                  icon={Clock}
                  title="Nothing in this selection"
                  description="Widen the time range or re-enable an activity type."
                />
              ) : (
                <TimelineChart data={filtered} />
              )}
            </Card>
          </div>

          <NotableMoments data={filtered} selectedDay={selectedDay} />
        </div>
      )}
    </PageShell>
  );
}
