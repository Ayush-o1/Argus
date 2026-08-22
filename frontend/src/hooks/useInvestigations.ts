import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  Confidence,
  Investigation,
  InvestigationHistory,
  InvestigationState,
  InvestigationSummary,
  Outcome,
  Vocabulary,
} from "@/lib/investigations";

export function useInvestigations(state?: InvestigationState | "") {
  return useQuery({
    queryKey: ["investigations", state ?? ""],
    queryFn: async () => {
      const search = new URLSearchParams({ page_size: "100" });
      if (state) search.set("state", state);
      // The envelope is kept rather than unwrapped to `.data`: `meta.total` is
      // the count over the whole table, and the page length is not it. Four
      // surfaces in this app once labelled a page with its own length.
      return apiFetch<InvestigationSummary[]>(`/api/investigations?${search.toString()}`);
    },
  });
}

export function useInvestigation(ref: string | undefined) {
  return useQuery({
    queryKey: ["investigations", "detail", ref],
    enabled: !!ref,
    queryFn: async () =>
      (await apiFetch<Investigation>(`/api/investigations/${encodeURIComponent(ref!)}`)).data,
  });
}

export function useInvestigationHistory(ref: string | undefined, asAt?: string) {
  return useQuery({
    queryKey: ["investigations", "history", ref, asAt ?? ""],
    enabled: !!ref,
    queryFn: async () => {
      const search = asAt ? `?at=${encodeURIComponent(asAt)}` : "";
      return (
        await apiFetch<InvestigationHistory>(
          `/api/investigations/${encodeURIComponent(ref!)}/history${search}`,
        )
      ).data;
    },
  });
}

/**
 * The controlled vocabularies, served by the backend that enforces them.
 *
 * Cached for the session: they change when a migration changes, not while
 * someone is working.
 */
export function useInvestigationVocabulary() {
  return useQuery({
    queryKey: ["investigations", "vocabulary"],
    staleTime: 30 * 60 * 1000,
    queryFn: async () =>
      (await apiFetch<Vocabulary>("/api/investigations/vocabulary")).data,
  });
}

export function useOutcomesByRule() {
  return useQuery({
    queryKey: ["investigations", "outcomes"],
    queryFn: async () =>
      (
        await apiFetch<{
          by_rule: { rule_id: string; rule_version: number; outcome: Outcome; investigations: number; alerts: number }[];
          by_outcome: Record<string, number>;
          closed_total: number;
          basis_note: string;
        }>("/api/investigations/outcomes")
      ).data,
  });
}

function useInvalidate(ref?: string) {
  const client = useQueryClient();
  return () => {
    client.invalidateQueries({ queryKey: ["investigations"] });
    if (ref) client.invalidateQueries({ queryKey: ["investigations", "detail", ref] });
  };
}

export interface OpenInvestigationPayload {
  title: string;
  hypothesis: string;
  confidence: Confidence;
  confidence_basis: string;
  assigned_to?: string | null;
  alert_keys?: string[];
}

export function useOpenInvestigation() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (payload: OpenInvestigationPayload) =>
      (
        await apiFetch<Investigation>("/api/investigations", {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
    onSuccess: invalidate,
  });
}

export function useTransitionInvestigation(ref: string | undefined) {
  const invalidate = useInvalidate(ref);
  return useMutation({
    mutationFn: async (payload: {
      to_state: InvestigationState;
      outcome?: Outcome;
      outcome_rationale?: string;
      note?: string;
    }) =>
      (
        await apiFetch<Investigation>(
          `/api/investigations/${encodeURIComponent(ref!)}/transition`,
          { method: "POST", body: JSON.stringify(payload) },
        )
      ).data,
    onSuccess: invalidate,
  });
}

export function useRecordFinding(ref: string | undefined) {
  const invalidate = useInvalidate(ref);
  return useMutation({
    mutationFn: async (payload: {
      statement: string;
      confidence: Confidence;
      cites: string[];
      supersedes?: string;
    }) =>
      (
        await apiFetch(`/api/investigations/${encodeURIComponent(ref!)}/findings`, {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
    onSuccess: invalidate,
  });
}

export function useReviewInvestigation(ref: string | undefined) {
  const invalidate = useInvalidate(ref);
  return useMutation({
    mutationFn: async (payload: { concurs: boolean; note?: string }) =>
      (
        await apiFetch(`/api/investigations/${encodeURIComponent(ref!)}/review`, {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
    onSuccess: invalidate,
  });
}

export function useLinkEvidence(ref: string | undefined) {
  const invalidate = useInvalidate(ref);
  return useMutation({
    mutationFn: async (payload: { entity_ref: string; entity_type: string; reason: string }) =>
      (
        await apiFetch(`/api/investigations/${encodeURIComponent(ref!)}/entities`, {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
    onSuccess: invalidate,
  });
}

/**
 * Record an analyst's own assessment of a subject, beside ARGUS's.
 *
 * Never replaces the model's. The response carries both bands and whether they
 * differ, so the caller can show the disagreement rather than just the winner.
 */
export function useRecordAnalystAssessment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      subject_ref: string;
      subject_type: string;
      analyst_band: string;
      rationale: string;
      confidence: Confidence;
      investigation_id?: string;
    }) =>
      (
        await apiFetch("/api/analyst-assessments", {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["investigations"] });
      client.invalidateQueries({ queryKey: ["analyst-assessments"] });
    },
  });
}

export function useAnalystAssessments(subjectRefs: string[]) {
  return useQuery({
    queryKey: ["analyst-assessments", subjectRefs],
    enabled: subjectRefs.length > 0,
    queryFn: async () => {
      const search = new URLSearchParams();
      subjectRefs.forEach((r) => search.append("subject_ref", r));
      return (
        await apiFetch<Record<string, import("@/lib/investigations").AnalystAssessment[]>>(
          `/api/analyst-assessments?${search.toString()}`,
        )
      ).data;
    },
  });
}
