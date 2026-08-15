import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Assertion, EntityProvenance, Source, SubjectProvenance } from "@/lib/provenance";

export function useSources() {
  return useQuery({
    queryKey: ["provenance-sources"],
    // The registry changes only when a source is added, so it is worth caching
    // across the session — a rating badge appears beside almost every value and
    // should not cost a request each time.
    staleTime: 5 * 60 * 1000,
    queryFn: async () => (await apiFetch<Source[]>("/api/provenance/sources")).data,
  });
}

export function useProvenanceSummary() {
  return useQuery({
    queryKey: ["provenance-summary"],
    staleTime: 5 * 60 * 1000,
    queryFn: async () =>
      (
        await apiFetch<{
          counts: Record<string, number>;
          synthetic_source_ids: string[];
          has_synthetic_data: boolean;
        }>("/api/provenance/summary")
      ).data,
  });
}

export function useEntityProvenance(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-provenance", entityId],
    enabled: !!entityId,
    queryFn: async () =>
      (await apiFetch<EntityProvenance>(`/api/entities/${encodeURIComponent(entityId!)}/provenance`))
        .data,
  });
}

/**
 * What ARGUS believed at a given instant.
 *
 * `asOf` null means now. It is part of the query key so switching the date
 * refetches rather than showing the previous instant's answer — an "as of"
 * view that lags the control it is driven by would be worse than not having one.
 */
export function useSubjectProvenance(
  entityId: string | undefined,
  asOf: string | null,
  includeEnded = false,
) {
  return useQuery({
    queryKey: ["subject-provenance", entityId, asOf, includeEnded],
    enabled: !!entityId,
    queryFn: async () => {
      const search = new URLSearchParams();
      if (asOf) search.set("as_of", asOf);
      if (includeEnded) search.set("include_ended", "true");
      const query = search.toString();
      return (
        await apiFetch<SubjectProvenance>(
          `/api/provenance/subjects/${encodeURIComponent(entityId!)}${query ? `?${query}` : ""}`,
        )
      ).data;
    },
  });
}

export interface CreateAssertionInput {
  subject_ref: string;
  predicate: string;
  object_value: unknown;
  epistemic_kind: "assessed" | "reported";
  reliability: string;
  credibility: string;
  note?: string | null;
  supporting_observation_ids?: string[];
  contradicting_observation_ids?: string[];
  supersedes?: string | null;
}

export function useCreateAssertion(entityId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateAssertionInput) =>
      (
        await apiFetch<Assertion>("/api/provenance/assertions", {
          method: "POST",
          body: JSON.stringify(input),
        })
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity-provenance", entityId] });
      queryClient.invalidateQueries({ queryKey: ["subject-provenance", entityId] });
    },
  });
}

export function useRetractAssertion(entityId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ assertionId, reason }: { assertionId: string; reason: string }) =>
      (
        await apiFetch<Assertion>(
          `/api/provenance/assertions/${encodeURIComponent(assertionId)}/retract`,
          { method: "POST", body: JSON.stringify({ reason }) },
        )
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["entity-provenance", entityId] });
      queryClient.invalidateQueries({ queryKey: ["subject-provenance", entityId] });
    },
  });
}
