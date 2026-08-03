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

export function useReviewAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ alertId, status }: { alertId: string; status: string }) =>
      (await apiFetch<Incident>(`/api/alerts/${alertId}/review`, { method: "PUT", body: JSON.stringify({ status }) })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}
