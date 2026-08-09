import { useQueries, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { CaseSummary, GraphNode, Incident, Subgraph, TimelineItem } from "@/lib/types";

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

/** Browse entities across multiple types with a shared risk floor and no name
 * text — /api/entities only accepts a single `type`, so this fans out one
 * request per type and merges. Used by Search's filter-only mode (the audit
 * flagged that the type/risk filter UI previously did nothing until the user
 * also typed a name). */
export function useBrowseEntities(types: string[], riskMin: number) {
  const queries = useQueries({
    queries: types.map((type) => ({
      queryKey: ["entities", { type, risk_min: riskMin, page_size: 50 }],
      queryFn: async () => {
        const search = new URLSearchParams({ type, page: "1", page_size: "50" });
        if (riskMin) search.set("risk_min", String(riskMin));
        return (await apiFetch<GraphNode[]>(`/api/entities?${search.toString()}`)).data;
      },
    })),
  });

  const isFetching = queries.some((q) => q.isFetching);
  const data = queries
    .flatMap((q) => q.data ?? [])
    .sort((a, b) => b.risk_score - a.risk_score);

  return { data, isFetching };
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

/** Cross-page linking (ARGUS_PLAN.md Phase 7): which Cases/Alerts this
 * entity is involved in, so its profile can jump straight into them instead
 * of the analyst re-searching for the same entity from Cases/Alerts. */
export function useEntityCases(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-cases", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<CaseSummary[]>(`/api/entities/${entityId}/cases`)).data,
  });
}

export function useEntityAlerts(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-alerts", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<Incident[]>(`/api/entities/${entityId}/alerts`)).data,
  });
}
