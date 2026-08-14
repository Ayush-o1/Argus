import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Subgraph } from "@/lib/types";

export function useSubgraph(entityId: string | undefined, depth = 1) {
  return useQuery({
    queryKey: ["subgraph", entityId, depth],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<Subgraph>(`/api/graph/subgraph?entity_id=${encodeURIComponent(entityId)}&depth=${depth}`)).data,
  });
}

export function useGraphOverview() {
  return useQuery({
    queryKey: ["graph-overview"],
    queryFn: async () => (await apiFetch<Subgraph>("/api/graph/overview")).data,
  });
}

export function useShortestPath(fromId: string | undefined, toId: string | undefined) {
  return useQuery({
    queryKey: ["shortest-path", fromId, toId],
    enabled: !!fromId && !!toId,
    queryFn: async () =>
      (await apiFetch<(Subgraph & { length: number }) | null>(`/api/graph/shortest-path?from_id=${fromId}&to_id=${toId}`)).data,
  });
}
