import type { GlobalTimeline } from "@/hooks/useTimeline";

/**
 * Pure temporal model behind the Timeline page.
 *
 * The page previously rendered one scatter of every sampled record, which shows
 * *that* activity exists but not what changed. Reconstructing a sequence of
 * events means asking: which days are unusual, what happened on them, and what
 * does the surrounding baseline look like. That requires bucketing and a stated
 * definition of "unusual", which is what lives here.
 */

export type LaneKey = "incidents" | "transactions" | "communications" | "events";

export const LANE_LABEL: Record<LaneKey, string> = {
  incidents: "Incidents",
  transactions: "Transactions",
  communications: "Communications",
  events: "Events",
};

export interface DayBucket {
  day: string; // ISO date (UTC)
  date: Date;
  total: number;
  flagged: number;
  incidents: number;
  /** Flagged volume more than BURST_SIGMA above the mean — a candidate burst. */
  burst: boolean;
}

export interface TimelineFilters {
  lanes: Record<LaneKey, boolean>;
  flaggedOnly: boolean;
  /** Days back from the newest record; null means the full window. */
  rangeDays: number | null;
}

export const DEFAULT_FILTERS: TimelineFilters = {
  lanes: { incidents: true, transactions: true, communications: true, events: true },
  flaggedOnly: false,
  rangeDays: null,
};

// A day is called a burst when its flagged volume exceeds the mean by this many
// standard deviations. Two sigma is the conventional starting point and, on
// this dataset, isolates a handful of days rather than a third of them — a
// threshold that fires constantly would be decoration, not a finding.
const BURST_SIGMA = 2;

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

interface RawRecord {
  timestamp: string;
  flagged: boolean;
  lane: LaneKey;
}

function collect(data: GlobalTimeline): RawRecord[] {
  return [
    ...data.incidents.map((i) => ({ timestamp: i.timestamp, flagged: true, lane: "incidents" as const })),
    ...data.transactions.map((t) => ({ timestamp: t.timestamp, flagged: t.flagged, lane: "transactions" as const })),
    ...data.communications.map((c) => ({ timestamp: c.timestamp, flagged: c.flagged, lane: "communications" as const })),
    ...data.events.map((e) => ({ timestamp: e.timestamp, flagged: e.flagged, lane: "events" as const })),
  ].filter((r) => Boolean(r.timestamp));
}

/** Newest timestamp across every record — the anchor for relative ranges. */
export function latestTimestamp(data: GlobalTimeline): Date | null {
  const times = collect(data).map((r) => Date.parse(r.timestamp)).filter((n) => !Number.isNaN(n));
  return times.length ? new Date(Math.max(...times)) : null;
}

export function rangeStart(data: GlobalTimeline, rangeDays: number | null): Date | null {
  if (rangeDays === null) return null;
  const latest = latestTimestamp(data);
  if (!latest) return null;
  return new Date(latest.getTime() - rangeDays * 86_400_000);
}

export function bucketByDay(data: GlobalTimeline, filters: TimelineFilters): DayBucket[] {
  const start = rangeStart(data, filters.rangeDays);
  const buckets = new Map<string, DayBucket>();

  for (const rec of collect(data)) {
    if (!filters.lanes[rec.lane]) continue;
    if (filters.flaggedOnly && !rec.flagged) continue;
    const time = Date.parse(rec.timestamp);
    if (Number.isNaN(time)) continue;
    if (start && time < start.getTime()) continue;

    const key = dayKey(rec.timestamp);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { day: key, date: new Date(`${key}T00:00:00Z`), total: 0, flagged: 0, incidents: 0, burst: false };
      buckets.set(key, bucket);
    }
    bucket.total += 1;
    if (rec.flagged) bucket.flagged += 1;
    if (rec.lane === "incidents") bucket.incidents += 1;
  }

  const ordered = [...buckets.values()].sort((a, b) => a.date.getTime() - b.date.getTime());
  markBursts(ordered);
  return ordered;
}

function markBursts(buckets: DayBucket[]): void {
  if (buckets.length < 3) return;
  const flagged = buckets.map((b) => b.flagged);
  const mean = flagged.reduce((sum, n) => sum + n, 0) / flagged.length;
  const variance = flagged.reduce((sum, n) => sum + (n - mean) ** 2, 0) / flagged.length;
  const sigma = Math.sqrt(variance);
  // With no spread every day is identical, so nothing is a burst — guarding
  // this avoids marking every day when sigma is 0.
  if (sigma === 0) return;
  const threshold = mean + BURST_SIGMA * sigma;
  for (const bucket of buckets) {
    if (bucket.flagged > threshold) bucket.burst = true;
  }
}

/** Filtered copy of the raw payload, for the lane scatter to render. */
export function applyFilters(data: GlobalTimeline, filters: TimelineFilters): GlobalTimeline {
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
    incidents: data.incidents.filter((i) => keep("incidents", true, i.timestamp)),
    transactions: data.transactions.filter((t) => keep("transactions", t.flagged, t.timestamp)),
    communications: data.communications.filter((c) => keep("communications", c.flagged, c.timestamp)),
    events: data.events.filter((e) => keep("events", e.flagged, e.timestamp)),
  };
}
