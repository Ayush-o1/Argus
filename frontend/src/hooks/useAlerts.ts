import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  Alert,
  AlertGroup,
  AlertModel,
  AlertState,
  AlertSuppression,
} from "@/lib/alerts";

export interface AlertQueueFilters {
  state?: AlertState | "";
  suppressed?: boolean;
  groupKey?: string;
  subjectRef?: string;
}

export function useAlerts(filters: AlertQueueFilters = {}) {
  return useQuery({
    queryKey: ["alerts", filters],
    queryFn: async () => {
      const search = new URLSearchParams({ page_size: "100" });
      if (filters.state) search.set("state", filters.state);
      if (filters.suppressed) search.set("suppressed", "true");
      if (filters.groupKey) search.set("group_key", filters.groupKey);
      if (filters.subjectRef) search.set("subject_ref", filters.subjectRef);
      return apiFetch<Alert[]>(`/api/alerts?${search.toString()}`);
    },
  });
}

export function useAlert(alertKey: string | undefined) {
  return useQuery({
    queryKey: ["alerts", "detail", alertKey],
    enabled: !!alertKey,
    queryFn: async () =>
      (await apiFetch<Alert>(`/api/alerts/${encodeURIComponent(alertKey!)}`)).data,
  });
}

/**
 * The queue rolled up to one row per story.
 *
 * A group is a correlated cluster ARGUS already published, not a similarity
 * heuristic invented at display time — and the count is over every alert in the
 * group rather than the page the client happens to hold.
 */
export function useAlertGroups() {
  return useQuery({
    queryKey: ["alerts", "groups"],
    queryFn: async () => (await apiFetch<AlertGroup[]>("/api/alerts/groups")).data,
  });
}

export function useAlertModel() {
  return useQuery({
    queryKey: ["alerts", "model"],
    staleTime: 5 * 60 * 1000,
    queryFn: async () => (await apiFetch<AlertModel>("/api/alerts/model")).data,
  });
}

export function useAlertSummary() {
  return useQuery({
    queryKey: ["alerts", "summary"],
    queryFn: async () =>
      (
        await apiFetch<{
          counts: Record<string, number>;
          latest_run: Record<string, unknown> | null;
          suppressed_note: string;
        }>("/api/alerts/summary")
      ).data,
  });
}

export function useSuppressions(activeOnly = true) {
  return useQuery({
    queryKey: ["alerts", "suppressions", activeOnly],
    queryFn: async () =>
      (
        await apiFetch<AlertSuppression[]>(
          `/api/alerts/suppressions?active_only=${activeOnly}`,
        )
      ).data,
  });
}

export function useAlertEvaluation() {
  return useQuery({
    queryKey: ["alerts", "evaluation"],
    queryFn: async () =>
      (await apiFetch<Record<string, unknown> | null>("/api/alerts/evaluation")).data,
  });
}

export function useTransitionAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      alertKey: string;
      to_state: AlertState;
      reason_code?: string | null;
      note?: string | null;
    }) =>
      (
        await apiFetch<Alert>(
          `/api/alerts/${encodeURIComponent(input.alertKey)}/transition`,
          {
            method: "POST",
            body: JSON.stringify({
              to_state: input.to_state,
              reason_code: input.reason_code ?? null,
              note: input.note ?? null,
            }),
          },
        )
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useAssignAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { alertKey: string; assignee: string | null }) =>
      (
        await apiFetch<Alert>(`/api/alerts/${encodeURIComponent(input.alertKey)}/assign`, {
          method: "POST",
          body: JSON.stringify({ assignee: input.assignee }),
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useCreateSuppression() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      rule_id: string | null;
      subject_ref: string | null;
      reason_code: string;
      note: string;
      expires_at: string;
    }) =>
      (
        await apiFetch<AlertSuppression>("/api/alerts/suppressions", {
          method: "POST",
          body: JSON.stringify(input),
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useRevokeSuppression() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (suppressionId: string) =>
      (
        await apiFetch<AlertSuppression>(
          `/api/alerts/suppressions/${encodeURIComponent(suppressionId)}`,
          { method: "DELETE" },
        )
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}
