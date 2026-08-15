import { useMutation, useQuery } from "@tanstack/react-query";
import { useHasPermission } from "@/hooks/useAuth";
import { apiFetch, ApiError } from "@/lib/api";

/** Probes for the optional local Ollama-backed assistant (ARGUS_PLAN.md
 * Phase 10). ARGUS Core has zero dependency on this — every other feature
 * works whether or not this query ever resolves to `available: true`. */
export function useAssistantStatus() {
  // Probed app-wide, so it must not fire for a role that cannot use it — an
  // administrator holds no entity:read permission and was getting a 403 on
  // every page load for a panel they can never open.
  const canUse = useHasPermission("entity:read");

  return useQuery({
    queryKey: ["assistant-status"],
    enabled: canUse,
    queryFn: async () => (await apiFetch<{ available: boolean }>("/api/ai/assistant-status")).data,
    staleTime: 30_000,
    retry: false,
  });
}

export function useAskAssistant() {
  return useMutation({
    mutationFn: async (question: string) => {
      try {
        return (await apiFetch<{ answer: string }>("/api/ai/ask", { method: "POST", body: JSON.stringify({ question }) }))
          .data;
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          throw new Error("Assistant not available — Ollama not detected");
        }
        throw err;
      }
    },
  });
}

export function useEntitySummary() {
  return useMutation({
    mutationFn: async (entityId: string) =>
      (await apiFetch<{ summary: string }>(`/api/ai/entity-summary/${encodeURIComponent(entityId)}`, { method: "POST" })).data,
  });
}

export function useCaseSummary() {
  return useMutation({
    mutationFn: async (caseId: string) =>
      (await apiFetch<{ summary: string }>(`/api/ai/case-summary/${encodeURIComponent(caseId)}`, { method: "POST" })).data,
  });
}
