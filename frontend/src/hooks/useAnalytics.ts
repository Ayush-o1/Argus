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
  avg_risk_score: number;
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
  risk_score: number;
}

export interface RiskPropagationEntry {
  id: string;
  name: string;
  label: string;
  propagated_risk: number;
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

export type AnalyticsResult =
  | RankedEntity[]
  | LouvainResult
  | SimilarEntity[]
  | RiskPropagationResult
  | Cycle[];

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
