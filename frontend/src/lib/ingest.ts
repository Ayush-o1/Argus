/** Client-side types for the ingestion surface. */

import type { ReliabilityCode } from "@/lib/provenance";

export interface ConnectorHealth {
  connector_id: string;
  display_name: string;
  source_id: string;
  source_name: string;
  connector_type: string;
  enabled: boolean;
  quarantined_at: string | null;
  quarantine_reason: string | null;
  poll_interval_seconds: number;
  last_run_at: string | null;
  last_success_at: string | null;
  source_reliability: ReliabilityCode;
  source_is_synthetic: boolean;
  /** The source's declared currency window. Null means none was declared, and
   * ARGUS says so rather than assuming one — a made-up threshold produces
   * made-up alerts. */
  staleness_hours: number | null;
  batches_24h: number;
  failed_batches_24h: number;
  records_24h: number;
  new_24h: number;
  failed_records_24h: number;
  open_failures: number;
}

export interface StaleSource extends ConnectorHealth {
  reason: string;
  /** `stopped` — was producing and has gone quiet. `never_produced` — has been
   * configured longer than its own expectation without a single successful
   * batch. Different problems: one is a feed that broke, the other is a feed
   * that never worked. */
  kind: "stopped" | "never_produced";
}

export interface IngestHealth {
  connectors: ConnectorHealth[];
  stale: StaleSource[];
  open_failures: number;
  queue: Record<string, number>;
  connector_types: string[];
}

export interface IngestFailure {
  failure_id: number;
  raw_id: number | null;
  connector_id: string;
  connector_name: string;
  batch_id: number | null;
  stage: "fetch" | "validate" | "normalize" | "persist";
  error_type: string;
  error_detail: string;
  occurred_at: string;
  replay_count: number;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution: string | null;
}

export const STAGE_MEANING: Record<IngestFailure["stage"], string> = {
  fetch: "ARGUS could not reach or read the source at all.",
  validate: "The record arrived but did not satisfy this source's mapping.",
  normalize: "A field could not be converted into the shape ARGUS stores.",
  persist: "The record was valid but could not be written.",
};
