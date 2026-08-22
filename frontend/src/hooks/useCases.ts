/**
 * Reads for the source case-record store.
 *
 * The mutations that used to live here — create, update, link and unlink
 * evidence — are gone. Every `Case` in the graph was written by the scenario
 * generator from a storyline, so analyst work recorded alongside them would be
 * indistinguishable from planted data a week later. The API returns 410 for
 * those routes and points at `/api/investigations`, which is a different object
 * in a different store: hypothesis, evidence, findings, an outcome, and an
 * append-only history with nothing generator-authored in it.
 */
import { useQuery } from "@tanstack/react-query";
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
    queryFn: async () => (await apiFetch<CaseDetail>(`/api/cases/${encodeURIComponent(caseId!)}`)).data,
  });
}

