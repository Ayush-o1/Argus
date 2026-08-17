import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAssessmentModel,
  fetchAssessmentQueue,
  fetchAssessmentSummary,
  fetchLatestEvaluation,
  fetchSubjectAssessment,
  requestAssessmentRun,
} from "@/lib/assessment";

/** The model is published so an analyst can read what ARGUS looks for. It
 * changes only on deploy, so it is cached hard. */
export function useAssessmentModel() {
  return useQuery({
    queryKey: ["assessment", "model"],
    queryFn: fetchAssessmentModel,
    staleTime: 60 * 60 * 1000,
  });
}

export function useAssessmentSummary() {
  return useQuery({
    queryKey: ["assessment", "summary"],
    queryFn: fetchAssessmentSummary,
  });
}

export function useAssessmentQueue(params: {
  band?: string;
  subject_type?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: ["assessment", "queue", params],
    queryFn: () => fetchAssessmentQueue(params),
  });
}

/**
 * One subject's assessment, including the working.
 *
 * `retry: false` because a 404 here is a real answer — ARGUS has not assessed
 * this subject — and retrying it three times before showing the reader that
 * answer just makes the truth arrive slower.
 */
export function useSubjectAssessment(subjectRef: string | undefined) {
  return useQuery({
    queryKey: ["assessment", "subject", subjectRef],
    enabled: !!subjectRef,
    retry: false,
    queryFn: () => fetchSubjectAssessment(subjectRef!),
  });
}

export function useLatestEvaluation() {
  return useQuery({
    queryKey: ["assessment", "evaluation"],
    queryFn: fetchLatestEvaluation,
  });
}

export function useRequestAssessmentRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (evaluate: boolean) => requestAssessmentRun(evaluate),
    onSuccess: () => {
      // The run is queued, not finished, so this refreshes the run list rather
      // than the results. Invalidating the assessments themselves here would
      // show the previous generation as though it were the new one.
      queryClient.invalidateQueries({ queryKey: ["assessment", "summary"] });
    },
  });
}
