import type { DayBucket, GlobalTimeline } from "@/hooks/useTimeline";

/**
 * Pure temporal model behind the Timeline page.
 *
 * Bucketing now happens server-side over the entire graph. This module filters
 * and analyses those buckets; it no longer counts records itself.
 *
 * What changed and why (audit B-03, B-18): burst detection used to run over a
 * random 800-record sample re-drawn on every request, with the mean taken only
 * across days that happened to appear in that sample. So the threshold moved
 * between refreshes, the "volume" it described was not volume, and empty days
 * were silently excluded from the baseline rather than counted as zero. The
 * statistic is only meaningful over a complete, contiguous series, which is
 * what the API now returns.
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
  flagged: number;
  incidents: number;
  /** Flagged volume more than BURST_SIGMA above the series mean. */
  burst: boolean;
}

export interface TimelineFilters {
  lanes: Record<LaneKey, boolean>;
  flaggedOnly: boolean;
  /** Days back from the newest bucket; null means the full window. */
  rangeDays: number | null;
}

export const DEFAULT_FILTERS: TimelineFilters = {
  lanes: { incidents: true, transactions: true, communications: true, events: true },
  flaggedOnly: false,
  rangeDays: null,
};

// Two sigma is the conventional starting point. A threshold that fires on a
// third of all days would be decoration rather than a finding.
export const BURST_SIGMA = 2;

/** Statistics behind the burst threshold, surfaced so the UI can state the
 * basis of its own claim rather than asserting "2σ" without showing the work. */
export interface BurstStats {
  mean: number;
  sigma: number;
  threshold: number;
  burstDays: number;
  /** Days in the analysed series — the denominator for the mean. */
  dayCount: number;
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
 * Flagged count restricted to the active lanes.
 *
 * The API returns flagged counts per lane, not just a per-day total, precisely
 * so this can be exact. A single summed total cannot be apportioned back to
 * individual lanes, which would have forced an approximation here — and a
 * figure the analyst reads as exact must not be an estimate.
 */
function flaggedForLanes(bucket: DayBucket, lanes: Record<LaneKey, boolean>): number {
  let flagged = 0;
  if (lanes.transactions) flagged += bucket.transactions_flagged;
  if (lanes.communications) flagged += bucket.communications_flagged;
  if (lanes.events) flagged += bucket.events_flagged;
  if (lanes.incidents) flagged += bucket.incidents_flagged;
  return flagged;
}

export function analyseDays(
  data: GlobalTimeline,
  filters: TimelineFilters,
): { days: AnalysedDay[]; stats: BurstStats } {
  const start = rangeStart(data, filters.rangeDays);

  const days: AnalysedDay[] = data.buckets
    .filter((b) => {
      if (!start) return true;
      return parseDay(b.day).getTime() >= start.getTime();
    })
    .map((b) => {
      const flagged = flaggedForLanes(b, filters.lanes);
      const total = filters.flaggedOnly ? flagged : totalForLanes(b, filters.lanes);
      return {
        day: b.day,
        date: parseDay(b.day),
        total,
        flagged,
        incidents: filters.lanes.incidents ? b.incidents : 0,
        burst: false,
      };
    });

  const stats = markBursts(days);
  return { days, stats };
}

/**
 * Mark days whose flagged volume exceeds the mean by BURST_SIGMA.
 *
 * The series is contiguous and zero-filled by the API, so days with no activity
 * are included in the mean as the zeroes they are.
 */
function markBursts(days: AnalysedDay[]): BurstStats {
  const empty: BurstStats = { mean: 0, sigma: 0, threshold: 0, burstDays: 0, dayCount: days.length };
  if (days.length < 3) return empty;

  const flagged = days.map((d) => d.flagged);
  const mean = flagged.reduce((sum, n) => sum + n, 0) / flagged.length;
  const variance = flagged.reduce((sum, n) => sum + (n - mean) ** 2, 0) / flagged.length;
  const sigma = Math.sqrt(variance);

  // With no spread every day is identical, so nothing stands out.
  if (sigma === 0) return { ...empty, mean };

  const threshold = mean + BURST_SIGMA * sigma;
  let burstDays = 0;
  for (const day of days) {
    if (day.flagged > threshold) {
      day.burst = true;
      burstDays += 1;
    }
  }

  return { mean, sigma, threshold, burstDays, dayCount: days.length };
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
  const start = rangeStart(data, filters.rangeDays);
  const inRange = (ts: string) => {
    if (!ts) return false;
    if (!start) return true;
    const time = Date.parse(ts);
    return !Number.isNaN(time) && time >= start.getTime();
  };
  const keep = (lane: LaneKey, flagged: boolean, ts: string) =>
    filters.lanes[lane] && inRange(ts) && (!filters.flaggedOnly || flagged);

  return {
    incidents: data.detail.incidents.records.filter((i) => keep("incidents", true, i.timestamp)),
    transactions: data.detail.transactions.records.filter((t) => keep("transactions", t.flagged, t.timestamp)),
    communications: data.detail.communications.records.filter((c) =>
      keep("communications", c.flagged, c.timestamp),
    ),
    events: data.detail.events.records.filter((e) => keep("events", e.flagged, e.timestamp)),
  };
}
