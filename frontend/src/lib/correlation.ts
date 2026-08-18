import { apiFetch } from "@/lib/api";

/**
 * ARGUS's own correlations, as the UI speaks about them.
 *
 * The vocabulary names how much corroboration was found, not how serious the
 * connection would be if real. `established` does not mean "confirmed
 * conspiracy" — it means two independent kinds of evidence identify this pair.
 * What the connection *means* is a judgement about the world, and ARGUS has no
 * evidence about intent.
 *
 * Two things every surface here must preserve:
 *
 *   - **The reason travels with the strength.** No component renders a number
 *     without the dimensions that produced it.
 *   - **Three states, not two.** A dimension can have fired, been evaluated and
 *     found nothing, or not been evaluable at all. `magnitude: null` is the
 *     third, and it must never be drawn as a zero.
 */

export type CorrelationTier = "established" | "probable" | "possible";

export interface DimensionOutcome {
  dimension_id: string;
  family: string;
  evaluable: boolean;
  /** Null when the dimension could not be evaluated — which is not the same as
   * 0, and the UI renders the two differently. */
  magnitude: number | null;
  contribution: number;
  summary: string;
  evidence: Record<string, unknown>;
}

export interface CorrelationLink {
  link_id: string;
  ref_a: string;
  ref_b: string;
  type_a: string;
  type_b: string;
  strength: number;
  tier: CorrelationTier;
  tier_meaning: string;
  /** Share of the dimensions applicable to this pair that could be evaluated.
   * Shown beside the strength everywhere, never instead of it. */
  coverage: number;
  evaluable_dimensions: number;
  applicable_dimensions: number;
  corroborating_families: string[];
  model_version: string;
  model_fingerprint: string;
  computed_at: string;
  dimensions: DimensionOutcome[];
}

export interface ClusterMember {
  subject_ref: string;
  subject_type: string;
  band: string;
  score: number | null;
  degree: number;
}

export interface CorrelatedCluster {
  cluster_id: string;
  cluster_key: string;
  size: number;
  families: string[];
  mean_strength: number;
  min_strength: number;
  /** Strength of the weakest link whose removal would split the group. Null
   * means every member is held by at least two independent routes — a
   * materially stronger claim than a group of the same size hanging off one. */
  weakest_bridge: number | null;
  bridge_count: number;
  over_merged: boolean;
  basis: string;
  model_version: string;
  model_fingerprint: string;
  computed_at: string;
  members: ClusterMember[];
}

export interface DimensionDefinition {
  dimension_id: string;
  family: string;
  label: string;
  question: string;
  rationale: string;
  reads: string[];
  subject_types: string[];
}

export interface ProjectionSpec {
  projection: string;
  title: string;
  description: string;
  fingerprint: string;
  node_labels: string[];
  relationships: {
    type: string;
    orientation: string;
    weight: number;
    weight_property: string | null;
    rationale: string;
  }[];
  caveats: string[];
}

export interface CorrelationModel {
  version: string;
  fingerprint: string;
  short_fingerprint: string;
  method: string;
  tiers: { tier: CorrelationTier; meaning: string }[];
  families: {
    family: string;
    meaning: string;
    ceiling: number;
    /** Whether this family can establish a link on its own or only corroborate
     * one. Published so "proximity is not evidence of association" can be
     * checked rather than believed. */
    identifying: boolean;
  }[];
  thresholds: Record<string, number>;
  dimensions: DimensionDefinition[];
  projections: ProjectionSpec[];
}

export interface CorrelationRun {
  run_id: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  model_version: string;
  model_fingerprint: string;
  assessment_run_id: number | null;
  anchors: number;
  candidate_pairs: number;
  links_recorded: number;
  clusters_found: number;
  keys_skipped: number;
  search_truncated: boolean;
  evidence_summary: Record<string, unknown>;
  triggered_by: string;
  error: string | null;
}

export interface CorrelationSummary {
  tier_counts: { tier: CorrelationTier; count: number; share: number | null; meaning: string }[];
  links_total: number;
  clusters_total: number;
  over_merged_clusters: number;
  clustered_subjects: number;
  last_run: CorrelationRun | null;
}

export interface SubjectCorrelation {
  subject_ref: string;
  links: CorrelationLink[];
  clusters: CorrelatedCluster[];
}

export interface PairMetrics {
  selected: number;
  true_positives: number;
  labelled_total: number;
  precision: number | null;
  recall: number | null;
}

export interface CorrelationEvaluation {
  evaluation_id: number;
  model_version: string;
  model_fingerprint: string;
  generated_at: string;
  report: {
    anchors: number;
    candidate_pairs: number;
    links_recorded: number;
    tier_counts: Record<string, number>;
    strict: PairMetrics;
    discriminative: PairMetrics;
    published_tiers: PairMetrics;
    unlabelled_links: number;
    both_planted_links: number;
    unlabelled_share: number | null;
    clusters: number;
    clustered_subjects: number;
    cluster_purity: number | null;
    over_merged_clusters: number;
    per_storyline: {
      storyline_type: string;
      planted_subjects: number;
      planted_pairs: number;
      recovered_pairs: number;
      pair_recall: number | null;
      reachable: boolean;
      note: string;
    }[];
    per_dimension: {
      dimension_id: string;
      family: string;
      evaluable: number;
      not_evaluable: number;
      fired: number;
      fired_on_labelled: number;
      precision_within_links: number | null;
    }[];
    caveats: string[];
  };
}

export const TIER_LABEL: Record<CorrelationTier, string> = {
  established: "Established",
  probable: "Probable",
  possible: "Possible",
};

export type TierTone = "critical" | "high" | "medium" | "low" | "neutral";

/** `possible` is neutral rather than green. It is a weak finding shown so it
 * can be dismissed with its reason visible, not a reassurance. */
export const TIER_TONE: Record<CorrelationTier, TierTone> = {
  established: "critical",
  probable: "medium",
  possible: "neutral",
};

export const FAMILY_LABEL: Record<string, string> = {
  financial: "Financial",
  social: "Social",
  logistical: "Logistical",
  spatial: "Spatial",
  temporal: "Temporal",
};

export function tierLabel(tier: string | null | undefined): string {
  if (!tier) return "Not correlated";
  return TIER_LABEL[tier as CorrelationTier] ?? tier;
}

/** Strengths are written to two places. A correlation is not precise enough to
 * justify more, and rounding to a whole number would make 0.44 and 0.45 —
 * either side of a tier boundary — look identical. */
export function formatStrength(strength: number | null | undefined): string | null {
  if (strength === null || strength === undefined) return null;
  return strength.toFixed(2);
}

export function formatCoverage(coverage: number | null | undefined): string | null {
  if (coverage === null || coverage === undefined) return null;
  return `${Math.round(coverage * 100)}%`;
}

/**
 * One phrase combining the two figures, used wherever a strength appears so no
 * surface can show the number alone.
 *
 * Deliberately says "of the model" rather than "confidence": a strength is how
 * much reason there is to think two findings belong together, not a probability
 * that they are acting in concert.
 */
export function strengthWithCoverage(
  strength: number | null | undefined,
  coverage: number | null | undefined,
): string {
  const value = formatStrength(strength);
  const share = formatCoverage(coverage);
  if (value === null) return "No link";
  if (share === null) return `strength ${value}`;
  return `strength ${value}, on ${share} of the dimensions that apply`;
}

/** What a dimension outcome is, in the three-state vocabulary. Centralised so
 * no component invents a fourth state or collapses two. */
export type DimensionState = "fired" | "clean" | "blind";

export function dimensionState(outcome: DimensionOutcome): DimensionState {
  if (!outcome.evaluable) return "blind";
  return (outcome.magnitude ?? 0) > 0 ? "fired" : "clean";
}

export async function fetchCorrelationModel() {
  return (await apiFetch<CorrelationModel>("/api/correlation/model")).data;
}

export async function fetchCorrelationSummary() {
  return (await apiFetch<CorrelationSummary>("/api/correlation/summary")).data;
}

export async function fetchCorrelationLinks(params: {
  tier?: string;
  page?: number;
  page_size?: number;
}) {
  const search = new URLSearchParams();
  if (params.tier) search.set("tier", params.tier);
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 25));
  return apiFetch<CorrelationLink[]>(`/api/correlation/links?${search.toString()}`);
}

export async function fetchSubjectCorrelation(subjectRef: string) {
  return (
    await apiFetch<SubjectCorrelation>(
      `/api/correlation/subject/${encodeURIComponent(subjectRef)}`,
    )
  ).data;
}

export async function fetchCorrelationClusters(limit = 25) {
  return (await apiFetch<CorrelatedCluster[]>(`/api/correlation/clusters?limit=${limit}`)).data;
}

export async function fetchCorrelationEvaluation() {
  return (await apiFetch<CorrelationEvaluation | null>("/api/correlation/evaluation")).data;
}

export async function requestCorrelationRun(evaluate: boolean) {
  return (
    await apiFetch<{ job_id: number | null; queued: boolean }>("/api/correlation/run", {
      method: "POST",
      body: JSON.stringify({ evaluate }),
    })
  ).data;
}
