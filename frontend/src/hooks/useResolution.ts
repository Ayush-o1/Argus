import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  Candidate,
  Cluster,
  Decision,
  EvaluationRow,
  QueueResponse,
  ResolutionRun,
} from "@/lib/resolution";

export function useResolutionQueue(band: string, entityType?: string) {
  return useQuery({
    queryKey: ["resolution-queue", band, entityType],
    queryFn: async () => {
      const search = new URLSearchParams({ band });
      if (entityType) search.set("entity_type", entityType);
      return (await apiFetch<QueueResponse>(`/api/resolution/queue?${search}`)).data;
    },
  });
}

export function useCandidate(candidateId: number | null) {
  return useQuery({
    queryKey: ["resolution-candidate", candidateId],
    enabled: candidateId !== null,
    queryFn: async () =>
      (await apiFetch<Candidate>(`/api/resolution/candidates/${candidateId}`)).data,
  });
}

export function useResolutionDecisions(limit = 25) {
  return useQuery({
    queryKey: ["resolution-decisions", limit],
    queryFn: async () =>
      (await apiFetch<Decision[]>(`/api/resolution/decisions?limit=${limit}`)).data,
  });
}

export function useClusters(contestedOnly = false) {
  return useQuery({
    queryKey: ["resolution-clusters", contestedOnly],
    queryFn: async () =>
      (
        await apiFetch<{ clusters: Cluster[]; counts: Record<string, number> }>(
          `/api/resolution/clusters?contested_only=${contestedOnly}`,
        )
      ).data,
  });
}

export function useResolutionRuns() {
  return useQuery({
    queryKey: ["resolution-runs"],
    queryFn: async () => (await apiFetch<ResolutionRun[]>("/api/resolution/runs")).data,
    // A sweep runs on the durable queue, so the page has to notice it finishing
    // without the analyst reloading.
    refetchInterval: 10_000,
  });
}

export function useEvaluations() {
  return useQuery({
    queryKey: ["resolution-evaluations"],
    queryFn: async () => (await apiFetch<EvaluationRow[]>("/api/resolution/evaluations")).data,
  });
}

/** Everything resolution knows about one record, for the entity profile. */
export function useEntityResolution(ref: string | null) {
  return useQuery({
    queryKey: ["resolution-entity", ref],
    enabled: !!ref,
    queryFn: async () =>
      (
        await apiFetch<{
          ref: string;
          exists: boolean;
          cluster: Cluster | null;
          same_as: { ref: string; decision_id: number; score: number | null; decided_by: string }[];
          candidates: Candidate[];
          decisions: Decision[];
        }>(`/api/resolution/entity/${encodeURIComponent(ref!)}`)
      ).data,
  });
}

function useResolutionMutation<TArgs>(
  path: (args: TArgs) => string,
  body?: (args: TArgs) => unknown,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: TArgs) =>
      apiFetch(path(args), {
        method: "POST",
        body: body ? JSON.stringify(body(args)) : undefined,
      }),
    onSuccess: () => {
      // A decision changes the queue, the clusters and the ledger at once —
      // leaving any of them stale would show an analyst a queue that still
      // contains the pair they just resolved.
      for (const key of [
        "resolution-queue",
        "resolution-clusters",
        "resolution-decisions",
        "resolution-candidate",
        "resolution-entity",
      ]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useDecideCandidate() {
  return useResolutionMutation<{
    candidateId: number;
    verdict: "same" | "different";
    rationale: string;
  }>(
    ({ candidateId }) => `/api/resolution/candidates/${candidateId}/decide`,
    ({ verdict, rationale }) => ({ verdict, rationale }),
  );
}

export function useReverseDecision() {
  return useResolutionMutation<{ decisionId: number; rationale: string }>(
    ({ decisionId }) => `/api/resolution/decisions/${decisionId}/reverse`,
    ({ rationale }) => ({ rationale }),
  );
}

export function useStartResolutionRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: { entityTypes?: string[]; applyAuto: boolean }) =>
      apiFetch("/api/resolution/runs", {
        method: "POST",
        body: JSON.stringify({ entity_types: args.entityTypes ?? null, apply_auto: args.applyAuto }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resolution-runs"] });
    },
  });
}

export function usePinCanonical() {
  return useResolutionMutation<{ ref: string; reason: string }>(
    () => "/api/resolution/clusters/pin",
    ({ ref, reason }) => ({ ref, reason }),
  );
}
