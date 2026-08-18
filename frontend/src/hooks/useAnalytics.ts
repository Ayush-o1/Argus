import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export interface RankedEntity {
  id: string;
  name: string;
  label: string;
  account_id: string;
  score: number;
}

export interface CommunityEntity {
  id: string;
  name: string;
  label: string;
}

export interface Community {
  community_id: number;
  size: number;
  /** Counts, not an average. Averaging assessment scores across a community
   * mixes subjects whose scores have different evidence denominators and
   * produces a figure that looks comparable between communities when it is
   * not. */
  assessed_members: number;
  flagged_members: number;
  top_entity: CommunityEntity;
}

export interface LouvainResult {
  communities: Community[];
  total_communities: number;
}

export interface SimilarEntity {
  id: string;
  name: string;
  label: string;
  similarity: number;
}

export interface RiskPropagationSeed {
  id: string;
  name: string;
  label: string;
  band: string | null;
  score: number | null;
}

export interface RiskPropagationEntry {
  id: string;
  name: string;
  label: string;
  propagated_risk: number;
}

export interface RiskPropagationResult {
  seeds: RiskPropagationSeed[];
  /** Seeds ARGUS has no assessment for. They are excluded from propagation
   * rather than defaulted to a starting value, and named so the analyst knows
   * their pick contributed nothing. */
  unusable_seeds: RiskPropagationSeed[];
  propagated: RiskPropagationEntry[];
  note: string;
}

export interface RiskPropagationResult {
  seeds: RiskPropagationSeed[];
  propagated: RiskPropagationEntry[];
}

export interface CycleMember {
  account_id: string;
  name: string;
  label: string;
  id: string;
}

export interface Cycle {
  length: number;
  total_amount: number;
  members: CycleMember[];
}

export interface TransactionAnomaly {
  id: string;
  name: string;
  label: string;
  account_id: string;
  tx_count: number;
  total_amount: number;
  max_burst_count: number;
  burst_window_hours: number;
  burst_baseline_mean: number;
  burst_baseline_std: number;
  z_score: number;
}

/**
 * A projection, as it travels with every graph-algorithm result.
 *
 * Before Phase 6 all of these ran on one hard-coded account-only graph and none
 * of them said so, which made "influence" mean "receives money from accounts
 * that receive money" while reading as something much broader. Every result now
 * carries the graph it was computed on.
 */
export interface ProjectionProvenance {
  projection: string;
  title: string;
  description: string;
  fingerprint: string;
  node_labels: string[];
  relationships: {
    type: string;
    orientation: string;
    weight: number;
    weight_property: string | null;
    rationale: string;
  }[];
  caveats: string[];
}

/** What the projection-based algorithms return: the numbers, and the graph. */
export interface ProjectedResult<T> {
  projection: ProjectionProvenance;
  results: T;
}

export type AnalyticsResult =
  | RankedEntity[]
  | LouvainResult
  | SimilarEntity[]
  | RiskPropagationResult
  | Cycle[]
  | TransactionAnomaly[];

export interface JobStatus<T = AnalyticsResult> {
  job_type: string | null;
  status: "running" | "done" | "failed";
  result: T | null;
  error: string | null;
}

const POLL_INTERVAL_MS = 1200;

/** Kicks off a POST job, then polls GET /api/analytics/results/:job_id until
 * it settles — the same "kick off -> poll -> get result" contract every
 * analytics endpoint follows (asyncio task + Redis job status). */
export function useAnalyticsJob<T = AnalyticsResult>() {
  const [jobId, setJobId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: async ({ path, body }: { path: string; body?: unknown }) =>
      (
        await apiFetch<{ job_id: string; status: string }>(path, {
          method: "POST",
          body: body !== undefined ? JSON.stringify(body) : undefined,
        })
      ).data,
    onSuccess: (data) => setJobId(data.job_id),
  });

  const job = useQuery({
    queryKey: ["analytics-job", jobId],
    queryFn: async () => (await apiFetch<JobStatus<T>>(`/api/analytics/results/${jobId}`)).data,
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? POLL_INTERVAL_MS : false),
  });

  const reset = () => setJobId(null);

  return { start, job, jobId, reset };
}
