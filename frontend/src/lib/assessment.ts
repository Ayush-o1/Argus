import { apiFetch } from "@/lib/api";

/**
 * ARGUS's own risk assessment, as the UI speaks about it.
 *
 * The vocabulary is deliberately not Critical/High/Medium/Low. Those name how
 * bad something is; these name what ARGUS found and how much of its model it
 * could apply. `insufficient_evidence` is a real band and outranks any score —
 * a subject ARGUS knows almost nothing about must never render as low risk.
 *
 * Everything here refuses a default. `score` is `number | null` all the way
 * through, because the previous `risk_score: number` defaulted to 0 and every
 * surface then drew a subject nobody had examined as a clean one.
 */

export type AssessmentBand = "elevated" | "notable" | "routine" | "insufficient_evidence";

export interface NodeAssessment {
  band: AssessmentBand;
  /** Null when the band is `insufficient_evidence`. Never 0. */
  score: number | null;
  /** Share of the model that could be evaluated for this subject. It is shown
   * beside the score everywhere, never instead of it and never omitted. */
  coverage: number | null;
  model?: string | null;
  assessed_at?: string | null;
}

export interface SignalOutcome {
  signal_id: string;
  family: string;
  weight: number;
  evaluable: boolean;
  /** Null when the signal could not be evaluated — which is not the same as 0,
   * and the UI must render the two differently. */
  magnitude: number | null;
  contribution: number;
  summary: string;
  detail: Record<string, unknown>;
}

export interface SubjectAssessment {
  subject_ref: string;
  subject_type: string;
  band: AssessmentBand;
  band_meaning: string;
  score: number | null;
  evidence_coverage: number;
  evaluable_weight: number;
  total_weight: number;
  families_fired: string[];
  model_version: string;
  model_fingerprint: string;
  computed_at: string;
  signals: SignalOutcome[];
}

export interface SignalDefinition {
  signal_id: string;
  title: string;
  question: string;
  family: string;
  weight: number;
  subject_types: string[];
  reads: string[];
  rationale: string;
}

export interface AssessmentModel {
  version: string;
  fingerprint: string;
  short_fingerprint: string;
  method: string;
  assessed_types: string[];
  bands: { band: AssessmentBand; meaning: string }[];
  thresholds: Record<string, number>;
  signals: SignalDefinition[];
}

export interface AssessmentSummary {
  band_counts: { band: string; count: number; share: number | null; meaning: string }[];
  assessed_total: number;
  last_run: {
    run_id: number;
    status: string;
    started_at: string;
    finished_at: string | null;
    model_version: string;
    model_fingerprint: string;
    evidence_summary: Record<string, number>;
    search_truncated: boolean;
    triggered_by: string;
    error: string | null;
  } | null;
}

export const BAND_LABEL: Record<AssessmentBand, string> = {
  elevated: "Elevated",
  notable: "Notable",
  routine: "Routine",
  insufficient_evidence: "Insufficient evidence",
};

/** Short forms for dense surfaces (map popups, graph legends). Never
 * abbreviated to the point of losing the distinction between "we looked and
 * found nothing" and "we could not look". */
export const BAND_SHORT: Record<AssessmentBand, string> = {
  elevated: "Elevated",
  notable: "Notable",
  routine: "Routine",
  insufficient_evidence: "Not assessable",
};

export type BandTone = "critical" | "high" | "medium" | "low" | "neutral";

/** `insufficient_evidence` is neutral, not quiet-green. It is an absence of
 * knowledge, and colouring it like a clean result is exactly the reassurance
 * this phase removed. */
export const BAND_TONE: Record<AssessmentBand, BandTone> = {
  elevated: "critical",
  notable: "medium",
  routine: "low",
  insufficient_evidence: "neutral",
};

export function bandLabel(band: string | null | undefined): string {
  if (!band) return "Not assessed";
  return BAND_LABEL[band as AssessmentBand] ?? band;
}

/** How a score should be written wherever one appears. Returns null when there
 * is no score, so a caller has to decide what to render instead of being handed
 * a "0". */
export function formatScore(score: number | null | undefined): string | null {
  if (score === null || score === undefined) return null;
  return Math.round(score).toString();
}

export function formatCoverage(coverage: number | null | undefined): string | null {
  if (coverage === null || coverage === undefined) return null;
  return `${Math.round(coverage * 100)}%`;
}

/** One sentence combining the two figures. Used wherever a score is shown, so
 * no surface can display the number on its own. */
export function scoreWithCoverage(
  score: number | null | undefined,
  coverage: number | null | undefined,
): string {
  const value = formatScore(score);
  const share = formatCoverage(coverage);
  if (value === null) return "No score — too little evidence to assess";
  if (share === null) return `${value} / 100`;
  return `${value} / 100, over ${share} of the model`;
}

export async function fetchAssessmentModel() {
  return (await apiFetch<AssessmentModel>("/api/assessment/model")).data;
}

export async function fetchAssessmentSummary() {
  return (await apiFetch<AssessmentSummary>("/api/assessment/summary")).data;
}

export async function fetchAssessmentQueue(params: {
  band?: string;
  subject_type?: string;
  page?: number;
  page_size?: number;
}) {
  const search = new URLSearchParams();
  if (params.band) search.set("band", params.band);
  if (params.subject_type) search.set("subject_type", params.subject_type);
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 25));
  return apiFetch<SubjectAssessment[]>(`/api/assessment/queue?${search.toString()}`);
}

export async function fetchSubjectAssessment(subjectRef: string) {
  return (
    await apiFetch<SubjectAssessment>(
      `/api/assessment/subject/${encodeURIComponent(subjectRef)}`,
    )
  ).data;
}

export interface EvaluationRecord {
  evaluation_id: number;
  model_version: string;
  model_fingerprint: string;
  generated_at: string;
  report: {
    subjects_assessed: number;
    labelled_subjects: number;
    labelled_by_storyline: number;
    labelled_by_injected_anomaly_only: number;
    band_counts: Record<string, number>;
    elevated: BandMetrics;
    elevated_storyline_only: BandMetrics;
    notable_or_better: BandMetrics;
    ranking: { top_k: number; labelled_in_top_k: number; share: number | null };
    per_storyline: {
      storyline_type: string;
      planted_subjects: number;
      reached_elevated: number;
      reached_notable_or_better: number;
      insufficient_evidence: number;
      recall_at_notable: number | null;
      detectable: boolean;
      note: string;
    }[];
    per_signal: {
      signal_id: string;
      evaluable: number;
      not_evaluable: number;
      fired: number;
      fired_on_labelled: number;
      fire_rate: number | null;
      precision: number | null;
    }[];
    caveats: string[];
  };
}

export interface BandMetrics {
  selected: number;
  true_positives: number;
  labelled_total: number;
  /** Null when nothing was selected — precision over an empty selection is
   * undefined, and rendering 0 would read as "everything it picked was wrong". */
  precision: number | null;
  recall: number | null;
}

export async function fetchLatestEvaluation() {
  return (await apiFetch<EvaluationRecord | null>("/api/assessment/evaluation")).data;
}

export async function requestAssessmentRun(evaluate: boolean) {
  return apiFetch<{ job_id: number | null; queued: boolean }>("/api/assessment/run", {
    method: "POST",
    body: JSON.stringify({ evaluate }),
  });
}

/**
 * Whether an entity's band satisfies a filter.
 *
 * An empty filter matches everything, including entities with no assessment —
 * "all entities" has to mean all of them, or the map silently becomes a view of
 * the assessed population presented as the whole world.
 *
 * `notable` is inclusive of `elevated` because a filter for "notable and above"
 * that excluded the strongest findings would be surprising in the one direction
 * that matters.
 */
export function matchesBand(band: string | null | undefined, filter: string): boolean {
  if (!filter) return true;
  if (filter === "notable") return band === "notable" || band === "elevated";
  return band === filter;
}
