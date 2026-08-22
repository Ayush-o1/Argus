/**
 * Investigation vocabulary, shared by the queue and the detail view.
 *
 * The outcomes, the confidence levels and their meanings come from the API
 * (`/api/investigations/vocabulary`), not from constants here. The backend owns
 * them — they are CHECK constraints in migration 009 — and a second copy in the
 * frontend would eventually offer an outcome the database rejects, which the
 * analyst would meet as a 500 at the moment they tried to finish their work.
 *
 * What lives here is presentation: tone mapping, ordering, and the phrasing
 * that turns a state into a sentence.
 */

export type InvestigationState = "open" | "active" | "closed";
export type Confidence = "low" | "moderate" | "high";
export type Outcome = "confirmed" | "unfounded" | "inconclusive" | "referred";

export interface InvestigationSummary {
  investigation_id: string;
  inv_ref: string;
  title: string;
  state: InvestigationState;
  confidence: Confidence;
  assigned_to: string | null;
  opened_by: string;
  opened_at: string;
  outcome: Outcome | null;
  closed_at: string | null;
  review_count: number;
  dissenting_reviews: number;
  last_reviewed_at: string | null;
  alert_count: number;
  entity_count: number;
  finding_count: number;
  open_action_count: number;
}

export interface InvestigationFinding {
  finding_id: string;
  statement: string;
  confidence: Confidence;
  cites: string[];
  author_username: string;
  author_role: string;
  recorded_at: string;
  superseded_by: string | null;
  superseded_at: string | null;
  withdrawn_at: string | null;
  withdrawn_by: string | null;
  withdrawal_reason: string | null;
}

export interface InvestigationEntity {
  link_id: number;
  entity_ref: string;
  entity_type: string;
  reason: string;
  linked_by: string;
  linked_at: string;
  removed_at: string | null;
  removed_by: string | null;
  removal_reason: string | null;
}

export interface InvestigationAlertLink {
  alert_key: string;
  attached_by: string;
  attached_at: string;
  attach_reason: string;
  detached_at: string | null;
  detached_by: string | null;
  detach_reason: string | null;
  rule_id: string;
  rule_version: number;
  title: string;
  priority_band: string;
  alert_state: string;
  scope: string[];
}

export interface InvestigationAction {
  action_id: string;
  description: string;
  assigned_to: string | null;
  due_at: string | null;
  recorded_by: string;
  recorded_at: string;
  completed_at: string | null;
  completed_by: string | null;
  completion_note: string | null;
}

export interface InvestigationReview {
  review_id: number;
  reviewer: string;
  reviewer_role: string;
  concurs: boolean;
  note: string | null;
  reviewed_at: string;
  outcome_reviewed: Outcome;
}

export interface AnalystAssessment {
  analyst_assessment_id: string;
  subject_ref: string;
  subject_type: string;
  analyst_band: string;
  rationale: string;
  confidence: Confidence;
  machine_band: string | null;
  machine_fingerprint: string | null;
  machine_computed_at: string | null;
  /** Null when ARGUS never assessed the subject — dissenting from nothing. */
  dissents: boolean | null;
  investigation_id: string | null;
  author_username: string;
  author_role: string;
  recorded_at: string;
}

export interface Investigation extends Omit<InvestigationSummary,
  "review_count" | "dissenting_reviews" | "last_reviewed_at" |
  "alert_count" | "entity_count" | "finding_count" | "open_action_count"> {
  hypothesis: string;
  confidence_basis: string;
  outcome_rationale: string | null;
  closed_by: string | null;
  alerts: InvestigationAlertLink[];
  entities: InvestigationEntity[];
  findings: InvestigationFinding[];
  actions: InvestigationAction[];
  reviews: InvestigationReview[];
  analyst_assessments: AnalystAssessment[];
}

export interface InvestigationEvent {
  event_id: number;
  event_type: string;
  field: string | null;
  old_value: unknown;
  new_value: unknown;
  note: string | null;
  actor_username: string;
  actor_role: string;
  occurred_at: string;
}

export interface InvestigationHistory {
  inv_ref: string;
  events: InvestigationEvent[];
  as_at: string | null;
  reconstructed: Record<string, unknown>;
  tracked_fields: string[];
  integrity: {
    consistent: boolean;
    break: null | {
      event_id: number;
      field: string;
      expected: unknown;
      recorded: unknown;
      occurred_at: string;
      describes: string;
    };
  };
}

export interface Vocabulary {
  states: { code: InvestigationState; meaning: string; may_move_to: string[] }[];
  outcomes: {
    code: Outcome;
    label: string;
    means: string;
    counts_as_correct: boolean | null;
  }[];
  outcome_note: string;
  confidence_levels: { code: Confidence; means: string }[];
  confidence_note: string;
  due_date_note: string;
}

/** Presentation only. The meanings come from the API. */
export const STATE_TONE: Record<InvestigationState, "open" | "active" | "closed"> = {
  open: "open",
  active: "active",
  closed: "closed",
};

export const OUTCOME_TONE: Record<Outcome, "confirmed" | "unfounded" | "neutral"> = {
  confirmed: "confirmed",
  unfounded: "unfounded",
  inconclusive: "neutral",
  referred: "neutral",
};

/**
 * The queue reads best with unfinished work first, newest within that.
 * Matches the API's own ordering rather than re-sorting a page client-side —
 * a client sort over one page of a longer list silently reorders a fraction.
 */
export const STATE_ORDER: InvestigationState[] = ["open", "active", "closed"];

export function describeState(state: InvestigationState, outcome: Outcome | null): string {
  if (state === "closed") {
    return outcome ? `Closed — ${outcome}` : "Closed";
  }
  return state === "open" ? "Not yet started" : "Being worked";
}

/**
 * A findings list shows superseded and withdrawn entries too, greyed rather
 * than hidden: how an analyst's understanding changed is part of the record,
 * and a list that quietly drops the retracted half reads as though the
 * conclusion was obvious all along.
 */
export function findingStanding(f: InvestigationFinding): "standing" | "superseded" | "withdrawn" {
  if (f.withdrawn_at) return "withdrawn";
  if (f.superseded_at) return "superseded";
  return "standing";
}
