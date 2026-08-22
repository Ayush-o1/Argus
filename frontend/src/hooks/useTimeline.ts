import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Aggregate } from "@/lib/aggregate";

export interface TimelineTransaction {
  id: string;
  timestamp: string;
  amount: number;
  subtype: string;
  source_reported: boolean;
}

export interface TimelineCommunication {
  id: string;
  timestamp: string;
  duration_seconds: number;
  subtype: string;
  source_reported: boolean;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  subtype: string;
  source_reported: boolean;
}

export interface TimelineIncident {
  id: string;
  timestamp: string;
  subtype: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  description: string;
}

/**
 * One day of activity, counted server-side across the entire graph.
 *
 * These counts are complete — not a sample. The previous implementation
 * received a random 800-record subset and computed daily volume from it, so the
 * histogram was labelled "volume" while showing something else entirely, and
 * every refresh produced different numbers.
 */
export interface DayBucket {
  day: string;
  total: number;
  source_reported: number;
  transactions: number;
  communications: number;
  events: number;
  incidents: number;
  /** Source-reported counts per lane. Returned separately from the day total so a lane
   * filter can produce an exact figure rather than an apportioned estimate. */
  transactions_source_reported: number;
  communications_source_reported: number;
  events_source_reported: number;
  incidents_source_reported: number;
}

/** A bounded, deterministically ordered preview of individual records, for the
 * scatter lane. Never a source for statistics — `coverage` states how much of
 * the lane it represents. */
export interface LanePreview<T> {
  records: T[];
  coverage: Aggregate<number>;
}

export interface GlobalTimeline {
  buckets: DayBucket[];
  day_count: number;
  totals: {
    records: Aggregate<number>;
    source_reported: Aggregate<number>;
    by_lane: Record<"transactions" | "communications" | "events" | "incidents", number>;
  };
  detail: {
    transactions: LanePreview<TimelineTransaction>;
    communications: LanePreview<TimelineCommunication>;
    events: LanePreview<TimelineEvent>;
    incidents: LanePreview<TimelineIncident>;
  };
}

export function useGlobalTimeline() {
  return useQuery({
    queryKey: ["timeline", "global"],
    queryFn: async () => (await apiFetch<GlobalTimeline>("/api/timeline/events")).data,
  });
}
