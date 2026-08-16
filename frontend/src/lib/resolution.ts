/** Client-side types for entity resolution. */

/** `not_comparable` is the important one.
 *
 * It means one of the two records simply does not carry the attribute, which
 * is neither agreement nor disagreement. Rendering it as a blank cell — or
 * worse, folding it in with the disagreements — would misrepresent what ARGUS
 * knows, so the review screen shows it as its own state with its own colour.
 */
export type Verdict = "agree" | "partial" | "disagree" | "not_comparable";

export type Band = "auto" | "review" | "insufficient" | "reject";

export interface AttributeComparison {
  key: string;
  label: string;
  left: unknown;
  right: unknown;
  score: number | null;
  weight: number;
  verdict: Verdict;
}

export interface Candidate {
  candidate_id: number;
  entity_type: string;
  left_ref: string;
  right_ref: string;
  /** Null when no attribute could be compared at all — a different statement
   * from a score of zero, and shown as "no basis" rather than "0.00". */
  score: number | null;
  /** The share of the model's total weight that was actually comparable — the
   * denominator for `score`. Never displayed apart from it. */
  evidence_weight: number;
  band: Band;
  band_reason: string;
  comparisons: AttributeComparison[];
  /** Why these two were ever compared. "They share a phone suffix" is a
   * materially different starting point from "their names sound alike". */
  blocking_keys: string[];
  model_version: string;
  model_fingerprint: string;
  status: "open" | "decided" | "withdrawn";
  created_at: string;
  updated_at: string;
  withdrawn_at: string | null;
  withdrawn_reason: string | null;
  history?: Decision[];
}

export interface Decision {
  decision_id: number;
  entity_type: string;
  left_ref: string;
  right_ref: string;
  verdict: "same" | "different";
  decided_by: string;
  /** Resolved at read time. Without it the byline is a raw uuid — the same
   * defect Phase 2 found in assertion attribution. */
  decided_by_display: string;
  decided_by_kind: "analyst" | "matcher";
  decided_at: string;
  rationale: string;
  score: number | null;
  evidence_weight: number | null;
  model_version: string | null;
  model_fingerprint: string | null;
  candidate_id: number | null;
  reverses_decision_id: number | null;
}

export interface ResolutionModel {
  version: string;
  fingerprint: string;
  auto_score: number;
  review_score: number;
  min_evidence_for_review: number;
  min_evidence_for_auto: number;
}

export interface QueueResponse {
  candidates: Candidate[];
  /** Every band and status, so the queue length is shown against what the
   * matcher considered rather than on its own. "14 pending" with no denominator
   * reads as "14 duplicates exist", which is a claim ARGUS cannot make. */
  counts: Record<string, Record<string, number>>;
  clusters: { clusters: number; members: number; contested: number };
  labels: Record<string, number>;
  model: ResolutionModel;
  supported_types: string[];
}

export interface Cluster {
  cluster_key: string;
  entity_type: string;
  canonical_ref: string;
  /** How the canonical record was chosen. "Canonical" is a choice, not a
   * discovery, and a surface presenting one record as *the* entity without
   * saying how it was picked is asserting something ARGUS was never told. */
  canonical_basis: string;
  member_count: number;
  contested: boolean;
  contested_reason: string | null;
  members: string[];
  rebuilt_at: string;
}

export interface ResolutionRun {
  run_id: number;
  entity_types: string[];
  model_version: string;
  model_fingerprint: string;
  status: "running" | "complete" | "failed";
  started_at: string;
  finished_at: string | null;
  profiles_examined: number;
  pairs_scored: number;
  auto_count: number;
  review_count: number;
  insufficient_count: number;
  reject_count: number;
  blocking_report: Record<string, unknown>;
  triggered_by: string;
  error: string | null;
}

export interface EvaluationRow {
  evaluation_id: number;
  model_version: string;
  model_fingerprint: string;
  dataset: "synthetic" | "analyst";
  ran_at: string;
  metrics: {
    overall: Record<string, number | null>;
    by_corruption?: Record<string, Record<string, number | null>>;
    note?: string;
    miss_count?: number;
    false_alarm_count?: number;
  };
  notes: string | null;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  agree: "Agrees",
  partial: "Partly",
  disagree: "Disagrees",
  not_comparable: "Not comparable",
};

export const BAND_MEANING: Record<Band, string> = {
  auto: "Merged by the matcher: an identifier matched exactly and nothing disagreed.",
  review: "A person decides. Similar enough to be worth looking at, not enough to act on.",
  insufficient: "Too little overlapping information to put in front of anyone.",
  reject: "Not the same record, or an identifying attribute disagreed.",
};

/** Formats a score without inventing one.
 *
 * A pair with nothing comparable has no score. Printing "0.00" there would say
 * "definitely different" when the truth is "no idea". */
export function formatScore(score: number | null): string {
  return score === null ? "no basis" : score.toFixed(2);
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
