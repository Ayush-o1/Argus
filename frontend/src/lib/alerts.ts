/**
 * Alert vocabulary, shared by the queue and the detail panel.
 *
 * The labels and their meanings come from the API (`/api/alerts/model`), not
 * from constants here — the backend owns the state machine, the dismissal
 * vocabulary and the priority bands, and a second copy in the frontend would
 * eventually disagree with it. What lives here is presentation: tone mapping,
 * formatting, and the ordering the queue reads best in.
 */

export type AlertState =
  | "open"
  | "acknowledged"
  | "investigating"
  | "resolved"
  | "dismissed";

export type PriorityBand = "high" | "medium" | "low";

export interface AlertPriorityFactors {
  priority: number;
  band: PriorityBand;
  factors: {
    corroboration: number;
    confidence: number;
    magnitude: number;
    recency: number;
  };
  independent_methods: number;
  evidence_age_days: number;
  asset_criticality: null;
  asset_criticality_note: string;
}

export interface Alert {
  alert_key: string;
  rule_id: string;
  rule_version: number;
  scope: string[];
  group_key: string | null;
  title: string;
  summary: string;
  priority: number;
  priority_band: PriorityBand;
  priority_factors: AlertPriorityFactors | Record<string, never>;
  evidence: Record<string, unknown>;
  state: AlertState;
  assigned_to: string | null;
  closed_at: string | null;
  dismissal_reason: string | null;
  suppressed: boolean;
  suppressed_by: string | null;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  transitions?: AlertTransition[];
  occurrences?: AlertOccurrence[];
  subjects?: AlertSubject[];
  spread?: AlertSpread;
}

export interface AlertSubject {
  subject_ref: string;
  subject_type: string | null;
  band: string | null;
  score: number | null;
  evidence_coverage: number | null;
  country: string | null;
  region: string | null;
}

export interface AlertSpread {
  countries: string[];
  country_count: number;
  regions: string[];
  region_count: number;
  subjects_total: number;
  subjects_located: number;
  /** "complete" when every subject has a recorded country. A spread computed
   * over 3 of 12 subjects is a different claim from one over all 12, so the
   * basis travels with the figures rather than being assumed. */
  basis: "complete" | "partial";
}

export interface AlertTransition {
  transition_id: number;
  from_state: AlertState | null;
  to_state: AlertState;
  reason_code: string | null;
  note: string | null;
  actor_username: string;
  actor_role: string;
  occurred_at: string;
}

export interface AlertOccurrence {
  occurrence_id: number;
  run_id: number;
  priority: number;
  magnitude: number;
  confidence: number;
  observed_at: string;
}

export interface AlertGroup {
  group_key: string;
  basis: string;
  subjects: string[];
  summary: string;
  alert_count: number;
  open_count: number;
  suppressed_count: number;
  top_priority: number | null;
  last_seen_at: string | null;
  rule_ids: string[];
}

export interface AlertRule {
  rule_id: string;
  version: number;
  title: string;
  means: string;
  would_be_wrong_if: string;
  reads: string[];
  independent_methods: number;
}

export interface DismissalReason {
  code: string;
  label: string;
  means: string;
  counts_as_false_positive: boolean;
}

export interface AlertModel {
  rules_fingerprint: string;
  rules: AlertRule[];
  states: { state: AlertState; meaning: string }[];
  transitions: Record<string, string[]>;
  dismissal_reasons: DismissalReason[];
  max_suppression_days: number;
  priority_note: string;
}

export interface AlertSuppression {
  suppression_id: string;
  rule_id: string | null;
  subject_ref: string | null;
  reason_code: string;
  note: string;
  created_by: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
}

export const STATE_LABEL: Record<AlertState, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  investigating: "Investigating",
  resolved: "Resolved",
  dismissed: "Dismissed",
};

type BadgeTone = "neutral" | "accent" | "critical" | "high" | "medium" | "low" | "ok";

export const STATE_TONE: Record<AlertState, BadgeTone> = {
  open: "high",
  acknowledged: "accent",
  investigating: "accent",
  resolved: "ok",
  dismissed: "neutral",
};

export const PRIORITY_TONE: Record<PriorityBand, BadgeTone> = {
  high: "critical",
  medium: "medium",
  low: "low",
};

export const RULE_LABEL: Record<string, string> = {
  "assessment.elevated": "Assessed elevated",
  "assessment.escalated": "Moved up a band",
  "correlation.established_pair": "Corroborated pair",
  "convergence.assessed_cluster": "Two methods concur",
};

export function formatPriority(value: number): string {
  return value.toFixed(2);
}

/**
 * How many subjects to show before summarising the rest.
 *
 * The number is shown alongside, always — a preview whose total is not stated
 * is exactly the defect the audit found on the old alert surface, where five
 * of twelve involved entities were presented as the alert's whole reach.
 */
export const SCOPE_PREVIEW = 4;
