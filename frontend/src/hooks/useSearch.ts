import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { GraphNode } from "@/lib/types";

export function useSearch(query: string) {
  return useQuery({
    queryKey: ["search", query],
    enabled: query.trim().length > 0,
    queryFn: async () => apiFetch<GraphNode[]>(`/api/search?q=${encodeURIComponent(query)}`),
  });
}
