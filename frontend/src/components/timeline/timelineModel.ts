import type { DayBucket, GlobalTimeline } from "@/hooks/useTimeline";

/**
 * Pure temporal model behind the Timeline page.
 *
 * Bucketing happens server-side over the entire graph. This module filters
 * those buckets; it counts nothing itself and now tests nothing itself.
 *
 * **Burst detection was removed from here.** It computed "days above the mean
 * plus two standard deviations" in the browser, and that was wrong in ways the
 * server-side aggregation (audit B-03, B-18) did not fix:
 *
 *   - the mean and σ were taken over the whole series *including* the bursts,
 *     so every unusual day raised the threshold meant to catch it;
 *   - "two sigma" is not a test — it has no null hypothesis and no error rate,
 *     and on count data the implied false-positive rate drifts with the volume;
 *   - it ran over whatever the user had filtered to, so toggling a lane changed
 *     which days were called bursts.
 *
 * Measured on the same data, that rule called 132 of 4,800 ordinary days a
 * burst. The replacement — a two-sided Poisson test of each day against the
 * rate implied by every *other* day, corrected across the series — calls one.
 * It lives on the server (`/api/patterns/temporal`), and this page renders its
 * answer rather than inventing its own.
 */

export type LaneKey = "incidents" | "transactions" | "communications" | "events";

export const LANE_LABEL: Record<LaneKey, string> = {
  incidents: "Incidents",
  transactions: "Transactions",
  communications: "Communications",
  events: "Events",
};

export const LANES: LaneKey[] = ["incidents", "transactions", "communications", "events"];

/** A server bucket, filtered to the active lanes and annotated with burst state. */
export interface AnalysedDay {
  day: string;
  date: Date;
  total: number;
  sourceReported: number;
  incidents: number;
  /** Set from the server's per-day Poisson test, not computed here. */
  unusual: boolean;
  unusualDirection: "high" | "low" | null;
}

export interface TimelineFilters {
  lanes: Record<LaneKey, boolean>;
  sourceReportedOnly: boolean;
  /** Days back from the newest bucket; null means the full window. */
  rangeDays: number | null;
  /** An interactive zoom into a sub-span of `rangeDays`, set by dragging a
   * selection across the histogram (epoch milliseconds, inclusive both
   * ends). Narrows further than `rangeDays` rather than replacing it — a
   * zoom is always "within what's currently on screen", so the two bounds
   * never disagree about which end is more restrictive. Cleared whenever
   * `rangeDays` changes: a pixel-drawn window from a 90-day view has no
   * reliable meaning once the view becomes 7 days. */
  zoomRange: { start: number; end: number } | null;
}

export const DEFAULT_FILTERS: TimelineFilters = {
  lanes: { incidents: true, transactions: true, communications: true, events: true },
  sourceReportedOnly: false,
  rangeDays: null,
  zoomRange: null,
};

/** The effective [start, end) window once `rangeDays` and an interactive
 * zoom are combined — the tighter bound wins on each side. `end` is null
 * (open, meaning "through the latest bucket") unless a zoom has bounded it. */
function windowBounds(data: GlobalTimeline, filters: TimelineFilters): { start: Date | null; end: Date | null } {
  const rangeStartDate = rangeStart(data, filters.rangeDays);
  if (!filters.zoomRange) return { start: rangeStartDate, end: null };

  const zoomStart = new Date(filters.zoomRange.start);
  const zoomEnd = new Date(filters.zoomRange.end);
  const start = rangeStartDate && rangeStartDate.getTime() > zoomStart.getTime() ? rangeStartDate : zoomStart;
  return { start, end: zoomEnd };
}

function parseDay(day: string): Date {
  // Buckets arrive as date-only keys — the server has already resolved each
  // timestamp to a day. Constructing at local midnight keeps the histogram's
  // x-axis aligned with the labels a reader sees, and deliberately does not
  // re-interpret the key as UTC: the day has already been decided, and shifting
  // it here would move events between buckets a second time.
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Newest bucket in the payload — the anchor for relative ranges. */
export function latestDay(data: GlobalTimeline): Date | null {
  if (!data.buckets.length) return null;
  return parseDay(data.buckets[data.buckets.length - 1].day);
}

export function rangeStart(data: GlobalTimeline, rangeDays: number | null): Date | null {
  if (rangeDays === null) return null;
  const latest = latestDay(data);
  if (!latest) return null;
  return new Date(latest.getTime() - rangeDays * 86_400_000);
}

/**
 * Recompute each day's total from the active lanes.
 *
 * The server returns per-lane counts precisely so lane toggles stay honest: with
 * only a single pre-summed total, unchecking "Events" could not actually remove
 * events from the figure, and the histogram would have kept showing them.
 */
function totalForLanes(bucket: DayBucket, lanes: Record<LaneKey, boolean>): number {
  let total = 0;
  if (lanes.transactions) total += bucket.transactions;
  if (lanes.communications) total += bucket.communications;
  if (lanes.events) total += bucket.events;
  if (lanes.incidents) total += bucket.incidents;
  return total;
}

/**
 * Source-reported count restricted to the active lanes.
 *
 * The API returns these per lane, not just a per-day total, precisely so this
 * can be exact. A single summed total cannot be apportioned back to individual
 * lanes, which would have forced an approximation — and a figure the analyst
 * reads as exact must not be an estimate.
 *
 * "Source-reported", not "flagged": it counts records the supplying source
 * marked, which in this world is the scenario generator marking the storylines
 * it planted. It is a fact about collection, not a finding.
 */
function sourceReportedForLanes(bucket: DayBucket, lanes: Record<LaneKey, boolean>): number {
  let reported = 0;
  if (lanes.transactions) reported += bucket.transactions_source_reported;
  if (lanes.communications) reported += bucket.communications_source_reported;
  if (lanes.events) reported += bucket.events_source_reported;
  if (lanes.incidents) reported += bucket.incidents_source_reported;
  return reported;
}

/**
 * Filter the server's buckets to the active lanes and range.
 *
 * `unusualDays` maps a date to the verdict of the server's per-day Poisson
 * test. It is passed in rather than computed: the test needs the whole series
 * and a baseline that excludes the day under test, neither of which survives
 * the user filtering a lane.
 */
export function analyseDays(
  data: GlobalTimeline,
  filters: TimelineFilters,
  unusualDays: Map<string, "high" | "low"> = new Map(),
): { days: AnalysedDay[] } {
  const { start, end } = windowBounds(data, filters);

  const days: AnalysedDay[] = data.buckets
    .filter((b) => {
      const t = parseDay(b.day).getTime();
      if (start && t < start.getTime()) return false;
      if (end && t > end.getTime()) return false;
      return true;
    })
    .map((b) => {
      const sourceReported = sourceReportedForLanes(b, filters.lanes);
      const total = filters.sourceReportedOnly ? sourceReported : totalForLanes(b, filters.lanes);
      const direction = unusualDays.get(b.day) ?? null;
      return {
        day: b.day,
        date: parseDay(b.day),
        total,
        sourceReported,
        incidents: filters.lanes.incidents ? b.incidents : 0,
        unusual: direction !== null,
        unusualDirection: direction,
      };
    });

  return { days };
}

/** The filtered record previews the scatter and ranked panel render. Distinct
 * from GlobalTimeline, which also carries the complete day buckets — the two
 * were previously the same shape, which is how record-level previews ended up
 * being used as a source for page-level statistics. */
export interface TimelineDetail {
  incidents: GlobalTimeline["detail"]["incidents"]["records"];
  transactions: GlobalTimeline["detail"]["transactions"]["records"];
  communications: GlobalTimeline["detail"]["communications"]["records"];
  events: GlobalTimeline["detail"]["events"]["records"];
}

/** Filtered record previews for the scatter lane. */
export function filterDetail(data: GlobalTimeline, filters: TimelineFilters): TimelineDetail {
  const { start, end } = windowBounds(data, filters);
  const inRange = (ts: string) => {
    if (!ts) return false;
    const time = Date.parse(ts);
    if (Number.isNaN(time)) return false;
    if (start && time < start.getTime()) return false;
    if (end && time > end.getTime()) return false;
    return true;
  };
  const keep = (lane: LaneKey, reported: boolean, ts: string) =>
    filters.lanes[lane] && inRange(ts) && (!filters.sourceReportedOnly || reported);

  return {
    incidents: data.detail.incidents.records.filter((i) => keep("incidents", true, i.timestamp)),
    transactions: data.detail.transactions.records.filter((t) => keep("transactions", t.source_reported, t.timestamp)),
    communications: data.detail.communications.records.filter((c) =>
      keep("communications", c.source_reported, c.timestamp),
    ),
    events: data.detail.events.records.filter((e) => keep("events", e.source_reported, e.timestamp)),
  };
}
