/**
 * Client-side vocabulary for provenance.
 *
 * The Admiralty axes are carried as separate strings the whole way from
 * Postgres to the screen. There is deliberately no helper here that turns a
 * rating into a number, a percentage or a bar width — the moment one exists,
 * some surface renders "72% confident" and the analyst loses the ability to
 * tell one excellent source from four poor ones.
 */

export type EpistemicKind = "observed" | "reported" | "inferred" | "assessed";

/** What a field's provenance lookup can conclude. `unattributed` is a real
 * outcome and is rendered as one: a value nothing accounts for must not look
 * like a value something does. */
export type AttributeKind = EpistemicKind | "unattributed" | "modified";

export type ReliabilityCode = "A" | "B" | "C" | "D" | "E" | "F";
export type CredibilityCode = "1" | "2" | "3" | "4" | "5" | "6";

export const RELIABILITY_MEANING: Record<ReliabilityCode, string> = {
  A: "Completely reliable",
  B: "Usually reliable",
  C: "Fairly reliable",
  D: "Not usually reliable",
  E: "Unreliable",
  F: "Reliability cannot be judged",
};

export const CREDIBILITY_MEANING: Record<CredibilityCode, string> = {
  "1": "Confirmed by independent sources",
  "2": "Probably true",
  "3": "Possibly true",
  "4": "Doubtful",
  "5": "Improbable",
  "6": "Credibility cannot be judged",
};

/** Written for a reader who has never met the Admiralty code. Every one of
 * these is about what the analyst should *do* with the value, because that is
 * the only reason the distinction is on screen. */
export const KIND_MEANING: Record<AttributeKind, string> = {
  observed:
    "Recorded directly by a system of record. The strongest footing ARGUS has.",
  reported:
    "A source claims this. ARGUS holds the claim, not the fact — weigh it by the source's reliability.",
  inferred:
    "Derived by an algorithm from other data. Only as good as the method, which is named alongside it.",
  assessed:
    "A named analyst's judgement. It may disagree with the machine, and that disagreement is preserved.",
  modified:
    "The stored value no longer matches what the source reported. Something changed it after the fact.",
  unattributed:
    "Nothing in the provenance store accounts for this value. Treat it as unsourced.",
};

export const KIND_LABEL: Record<AttributeKind, string> = {
  observed: "Observed",
  reported: "Reported",
  inferred: "Inferred",
  assessed: "Assessed",
  modified: "Modified",
  unattributed: "Unattributed",
};

export interface Rating {
  reliability: ReliabilityCode;
  credibility: CredibilityCode;
}

export interface Source {
  source_id: string;
  name: string;
  source_type: string;
  description: string;
  reliability: ReliabilityCode;
  reliability_basis: string;
  is_synthetic: boolean;
  independence_group: string;
  staleness_hours: number | null;
  is_active: boolean;
  registered_at: string | null;
}

export interface EvidenceRef {
  observation_id: string;
  stance: "supports" | "contradicts";
  source_id: string;
  source_name: string;
  source_reliability: ReliabilityCode;
  source_is_synthetic: boolean;
  recorded_at: string;
  occurred_at: string | null;
  collected_at: string | null;
}

export interface Corroboration {
  independent_sources: number;
  supporting_observations: number;
  contradicting_observations: number;
  source_groups: string[];
  contradicting_groups: string[];
}

export interface Assertion {
  assertion_id: string;
  subject_ref: string;
  subject_type: string;
  predicate: string;
  object_value: unknown;
  epistemic_kind: EpistemicKind;
  rating: Rating;
  method: string;
  /** Stable identity — `user:<uuid>` or `source:<id>`. Never displayed raw. */
  asserted_by: string;
  /** The same attribution, readable. Resolved server-side against the user and
   * source tables; falls back to the raw identifier when the referent is gone. */
  asserted_by_display: string;
  asserted_at: string;
  valid_from: string | null;
  valid_until: string | null;
  superseded_by: string | null;
  superseded_at: string | null;
  retracted_at: string | null;
  retracted_by: string | null;
  retracted_by_display: string | null;
  retraction_reason: string | null;
  note: string | null;
  evidence: EvidenceRef[];
  corroboration: Corroboration | null;
}

export interface Conflict {
  subject_ref: string;
  predicate: string;
  assertions: Assertion[];
}

export interface ObservationRef {
  observation_id: string;
  source_id: string;
  source_name: string;
  source_reliability: ReliabilityCode;
  source_is_synthetic: boolean;
  recorded_at: string;
  collected_at: string | null;
  occurred_at: string | null;
  reported_value: unknown;
  matches_current_value: boolean;
}

export interface AttributeProvenance {
  kind: AttributeKind;
  observations: ObservationRef[];
  assertions: Assertion[];
}

export interface EntityProvenance {
  subject_ref: string;
  attributes: Record<string, AttributeProvenance>;
  /** How many observations the per-attribute resolution actually read, against
   * how many exist. When these differ, an `unattributed` field may simply be
   * one whose observation fell outside the window — a distinction the UI has to
   * make, because the two mean entirely different things. */
  observations_examined: number;
  observations_total: number;
  attributes_complete: boolean;
  assertions: Assertion[];
  conflicts: Conflict[];
  sources: Source[];
}

export interface Observation {
  observation_id: string;
  source_id: string;
  source_name: string;
  source_reliability: ReliabilityCode;
  source_is_synthetic: boolean;
  content_type: string;
  payload: Record<string, unknown>;
  content_hash: string;
  occurred_at: string | null;
  collected_at: string | null;
  recorded_at: string;
  supersedes: string | null;
  provenance_note: string | null;
  subjects: string[];
}

export interface SubjectProvenance {
  subject_ref: string;
  as_of: string | null;
  observations: Observation[];
  /** The denominator for `observations`, which is a bounded read. */
  observation_total: number;
  assertions: Assertion[];
  conflicts: Conflict[];
  sources: Source[];
}

/** "not recorded", not a plausible-looking date.
 *
 * Every timestamp in this layer can legitimately be absent, and the whole point
 * of the layer is that an absence is shown as an absence. */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "not recorded";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function describeValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
