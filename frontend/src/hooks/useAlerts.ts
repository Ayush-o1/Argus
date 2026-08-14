import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Incident } from "@/lib/types";

export function useAlerts(status?: string, priority?: string) {
  return useQuery({
    queryKey: ["alerts", status, priority],
    queryFn: async () => {
      const search = new URLSearchParams({ page_size: "100" });
      if (status) search.set("status", status);
      if (priority) search.set("priority", priority);
      return apiFetch<Incident[]>(`/api/alerts?${search.toString()}`);
    },
  });
}

/**
 * Alerts sharing this one's storyline, resolved server-side across the whole
 * graph. The UI used to filter the currently-loaded page for this, so anything
 * beyond the first 100 alerts was invisible while the panel claimed to identify
 * a single investigation (audit B-29).
 */
export function useRelatedAlerts(alertId: string | undefined) {
  return useQuery({
    queryKey: ["alerts", "related", alertId],
    enabled: !!alertId,
    queryFn: async () =>
      (await apiFetch<Incident[]>(`/api/alerts/${encodeURIComponent(alertId!)}/related`)).data,
  });
}

export function useReviewAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ alertId, status }: { alertId: string; status: string }) =>
      (await apiFetch<Incident>(`/api/alerts/${alertId}/review`, { method: "PUT", body: JSON.stringify({ status }) })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}
