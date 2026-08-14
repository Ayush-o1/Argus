import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { CaseDetail, CaseSummary } from "@/lib/types";

export function useCases(status?: string) {
  return useQuery({
    queryKey: ["cases", status],
    queryFn: async () => {
      const search = new URLSearchParams({ page_size: "100" });
      if (status) search.set("status", status);
      return apiFetch<CaseSummary[]>(`/api/cases?${search.toString()}`);
    },
  });
}

export function useCase(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case", caseId],
    enabled: !!caseId,
    queryFn: async () => (await apiFetch<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`)).data,
  });
}

export function useCreateCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title: string; priority: string; notes?: string }) =>
      (await apiFetch<CaseDetail>("/api/cases", { method: "POST", body: JSON.stringify(payload) })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cases"] }),
  });
}

export function useUpdateCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<{ status: string; priority: string; notes: string; assigned_analyst: string }>) =>
      (await apiFetch<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`, { method: "PUT", body: JSON.stringify(payload) })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case", caseId] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });
}

export function useAddCaseEntity(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { entity_id: string; reason?: string }) =>
      (await apiFetch<{ linked: boolean }>(`/api/cases/${encodeURIComponent(caseId)}/entities`, { method: "POST", body: JSON.stringify(payload) }))
        .data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
  });
}

export function useRemoveCaseEntity(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (entityId: string) =>
      (await apiFetch<{ removed: boolean }>(`/api/cases/${encodeURIComponent(caseId)}/entities/${encodeURIComponent(entityId)}`, { method: "DELETE" })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
  });
}
