import { useQueries, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { CaseSummary, GraphNode, Incident, Subgraph, TimelineItem } from "@/lib/types";

interface ListEntitiesParams {
  type?: string;
  /** An assessment band, not a score floor. A score is a share of whatever
   * could be evaluated for that subject, so a numeric threshold across mixed
   * subject types compares numbers with different denominators. */
  band?: string;
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
      if (params.band) search.set("band", params.band);
      if (params.city) search.set("city", params.city);
      search.set("page", String(params.page ?? 1));
      search.set("page_size", String(params.page_size ?? 50));
      return apiFetch<GraphNode[]>(`/api/entities?${search.toString()}`);
    },
  });
}

/** Browse entities across multiple types with a shared assessment band and no
 * name text — /api/entities only accepts a single `type`, so this fans out one
 * request per type and merges. Used by Search's filter-only mode (the audit
 * flagged that the type/risk filter UI previously did nothing until the user
 * also typed a name). */
export function useBrowseEntities(types: string[], band: string | null) {
  const queries = useQueries({
    queries: types.map((type) => ({
      queryKey: ["entities", { type, band, page_size: 50 }],
      queryFn: async () => {
        const search = new URLSearchParams({ type, page: "1", page_size: "50" });
        if (band) search.set("band", band);
        return (await apiFetch<GraphNode[]>(`/api/entities?${search.toString()}`)).data;
      },
    })),
  });

  const isFetching = queries.some((q) => q.isFetching);
  // Unassessed entities sort last rather than to either extreme: they are not
  // the most interesting and they are not the least, because nothing is known.
  const data = queries.flatMap((q) => q.data ?? []).sort(byAssessmentScore);

  return { data, isFetching };
}

export function byAssessmentScore(a: GraphNode, b: GraphNode): number {
  const left = a.assessment?.score;
  const right = b.assessment?.score;
  if (left === null || left === undefined) return right === null || right === undefined ? 0 : 1;
  if (right === null || right === undefined) return -1;
  return right - left;
}

export function useEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<GraphNode>(`/api/entities/${encodeURIComponent(entityId!)}`)).data,
  });
}

export function useEntityGraph(entityId: string | undefined, depth = 1) {
  return useQuery({
    queryKey: ["entity-graph", entityId, depth],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<Subgraph>(`/api/entities/${encodeURIComponent(entityId!)}/graph?depth=${depth}`)).data,
  });
}

export function useEntityTimeline(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-timeline", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<TimelineItem[]>(`/api/entities/${encodeURIComponent(entityId!)}/timeline`)).data,
  });
}

/** Cross-page linking (ARGUS_PLAN.md Phase 7): which Cases/Alerts this
 * entity is involved in, so its profile can jump straight into them instead
 * of the analyst re-searching for the same entity from Cases/Alerts. */
export function useEntityCases(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-cases", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<CaseSummary[]>(`/api/entities/${encodeURIComponent(entityId!)}/cases`)).data,
  });
}

export function useEntityAlerts(entityId: string | undefined) {
  return useQuery({
    queryKey: ["entity-alerts", entityId],
    enabled: !!entityId,
    queryFn: async () => (await apiFetch<Incident[]>(`/api/entities/${encodeURIComponent(entityId!)}/alerts`)).data,
  });
}
