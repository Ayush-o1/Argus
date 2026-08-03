import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { GraphNode, Subgraph, TimelineItem } from "@/lib/types";

interface ListEntitiesParams {
  type?: string;
  risk_min?: number;
  city?: string;
  page?: number;
  page_size?: number;
}

export function useEntities(params: ListEntitiesParams) {
  return useQuery({
    queryKey: ["entities", params],
    queryFn: async () => {
      const search = new URLSearchParams();
      if (params.type) search.set("type", params.type);
      if (params.risk_min) search.set("risk_min", String(params.risk_min));
      if (params.city) search.set("city", params.city);
      search.set("page", String(params.page ?? 1));
      search.set("page_size", String(params.page_size ?? 50));
      return apiFetch<GraphNode[]>(`/api/entities?${search.toString()}`);
    },
  });
}

export function useEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<GraphNode>(`/api/entities/${entityId}`)).data,
  });
}

export function useEntityGraph(entityId: string | undefined, depth = 1) {
  return useQuery({
    queryKey: ["entity-graph", entityId, depth],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<Subgraph>(`/api/entities/${entityId}/graph?depth=${depth}`)).data,
  });
}

export function useEntityTimeline(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-timeline", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<TimelineItem[]>(`/api/entities/${entityId}/timeline`)).data,
  });
}
