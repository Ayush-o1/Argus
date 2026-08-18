import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchCorrelationClusters,
  fetchCorrelationEvaluation,
  fetchCorrelationLinks,
  fetchCorrelationModel,
  fetchCorrelationSummary,
  fetchSubjectCorrelation,
  requestCorrelationRun,
} from "@/lib/correlation";

/** The model is published so an analyst can read what ARGUS treats as a
 * connection. It changes only on deploy, so it is cached hard. */
export function useCorrelationModel() {
  return useQuery({
    queryKey: ["correlation", "model"],
    queryFn: fetchCorrelationModel,
    staleTime: 60 * 60 * 1000,
  });
}

export function useCorrelationSummary() {
  return useQuery({
    queryKey: ["correlation", "summary"],
    queryFn: fetchCorrelationSummary,
  });
}

export function useCorrelationLinks(params: {
  tier?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: ["correlation", "links", params],
    queryFn: () => fetchCorrelationLinks(params),
  });
}

export function useCorrelationClusters(limit = 25) {
  return useQuery({
    queryKey: ["correlation", "clusters", limit],
    queryFn: () => fetchCorrelationClusters(limit),
  });
}

/**
 * Everything ARGUS links one subject to.
 *
 * `retry: false` because an empty result here is a real answer — ARGUS found no
 * correlation — and the endpoint returns 200 with empty lists rather than a
 * 404, so there is nothing to retry into.
 */
export function useSubjectCorrelation(subjectRef: string | undefined) {
  return useQuery({
    queryKey: ["correlation", "subject", subjectRef],
    enabled: !!subjectRef,
    retry: false,
    queryFn: () => fetchSubjectCorrelation(subjectRef!),
  });
}

export function useCorrelationEvaluation() {
  return useQuery({
    queryKey: ["correlation", "evaluation"],
    queryFn: fetchCorrelationEvaluation,
  });
}

export function useRequestCorrelationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (evaluate: boolean) => requestCorrelationRun(evaluate),
    onSuccess: () => {
      // The run is queued, not finished, so this refreshes the run status
      // rather than the results. Invalidating the links here would redraw the
      // previous generation as though it were the new one.
      queryClient.invalidateQueries({ queryKey: ["correlation", "summary"] });
    },
  });
}
