import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export interface ScenarioTypes {
  types: string[];
  complexities: string[];
}

export interface ScenarioResult {
  storyline_id: string;
  type: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  description: string;
  case_id: string | null;
  key_entity_id: string;
  key_entity_name: string;
  node_counts: Record<string, number>;
  seed: number;
  stages: string[];
}

export interface ScenarioJobStatus {
  job_type: string | null;
  status: "running" | "done" | "failed";
  result: ScenarioResult | null;
  error: string | null;
  stages: string[];
}

const POLL_INTERVAL_MS = 900;

export function useScenarioTypes() {
  return useQuery({
    queryKey: ["scenario-types"],
    queryFn: async () => (await apiFetch<ScenarioTypes>("/api/scenario/types")).data,
    staleTime: Infinity,
  });
}

export function useScenarioJob() {
  const [jobId, setJobId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: async (payload: { type: string; complexity: string; seed: number | null }) =>
      (await apiFetch<{ job_id: string }>("/api/scenario/generate", { method: "POST", body: JSON.stringify(payload) }))
        .data,
    onSuccess: (data) => setJobId(data.job_id),
  });

  const job = useQuery({
    queryKey: ["scenario-job", jobId],
    queryFn: async () => (await apiFetch<ScenarioJobStatus>(`/api/scenario/status/${jobId}`)).data,
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? POLL_INTERVAL_MS : false),
  });

  const reset = () => setJobId(null);

  return { start, job, jobId, reset };
}
