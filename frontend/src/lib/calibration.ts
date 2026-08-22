/**
 * Calibration and export types.
 *
 * The interval fields are not optional decoration. Nothing in this app should
 * render `point` without `ci_low`/`ci_high` beside it — the whole argument of
 * the calibration phase is that a proportion without its interval is not a
 * measurement, and a component that showed one and not the other would undo it
 * in the one place a reader actually looks.
 */

export interface Proportion {
  successes: number;
  trials: number;
  point: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_method: string;
  confidence_level: number;
  /** False when the interval is too wide to separate a good rule from a bad one. */
  informative: boolean;
  describes: string;
}

export interface RuleCalibration {
  rule_id: string;
  rule_version: number;
  alerts: number;
  firings: number;
  still_open: number;
  suppressed: number;
  has_feedback: boolean;
  triage: {
    dismissed: number;
    dismissed_as_wrong: number;
    by_reason: Record<string, number>;
    precision: Proportion;
    note: string;
  };
  outcomes: {
    confirmed: number;
    unfounded: number;
    did_not_settle: number;
    precision: Proportion;
    note: string;
  };
}

export interface CalibrationReport {
  rules: RuleCalibration[];
  summary: {
    rules: number;
    rules_with_any_feedback: number;
    rules_without_feedback: number;
    outcome_precision_pooled: Proportion;
    triage_precision_pooled: Proportion;
    pooling_note: string;
    coverage_note: string;
  };
  informative_width: number;
  method_note: string;
}

export interface FalseNegatives {
  investigations: {
    investigation_id: string;
    inv_ref: string;
    title: string;
    opened_by: string;
    opened_at: string;
    state: string;
    outcome: string | null;
  }[];
  total: number;
  confirmed: number;
  is_a_lower_bound: boolean;
  note: string;
}

export interface DriftComparison {
  earlier_run_id: number;
  later_run_id: number;
  same_model: boolean;
  evaluable: boolean;
  shifted: boolean;
  p_value: number | null;
  describes: string;
  cannot_distinguish: string;
}

export interface DriftReport {
  runs: {
    run_id: number;
    model_fingerprint: string;
    started_at: string;
    subjects_assessed: number;
    elevated_count: number;
    notable_count: number;
    routine_count: number;
    insufficient_count: number;
  }[];
  comparisons: DriftComparison[];
  evaluable: boolean;
  note: string;
}

export interface SimulationResult {
  changes: string[];
  no_change: boolean;
  current_total: number;
  candidate_total: number;
  unchanged: number;
  added: number;
  removed: number;
  per_rule: { rule_id: string; unchanged: number; added: number; removed: number }[];
  added_examples: { rule_id: string; scope: string[]; title: string }[];
  feedback_on_removed: Record<string, number>;
  removed_with_confirmed_outcome: string[];
  what_this_does_not_say: string;
  read_the_removals_first: string;
  activation_note: string;
}

export type ClassificationCode =
  | "unrestricted"
  | "internal"
  | "confidential"
  | "restricted";

export interface ClassificationLevel {
  code: ClassificationCode;
  label: string;
  rank: number;
  means: string;
  handling: string;
  export_retention_days: number;
}

export interface ExportRecord {
  export_id: string;
  investigation_id: string | null;
  format: "json" | "html";
  classification: ClassificationCode;
  content_sha256: string;
  byte_size: number;
  requested_by: string;
  requester_role: string;
  requester_clearance: string;
  requested_at: string;
  purpose: string;
  retention_until: string;
  disposed_at: string | null;
  disposed_by: string | null;
  disposal_reason: string | null;
}

export interface ExportAccess {
  access_id: number;
  action: string;
  actor_username: string;
  actor_role: string;
  actor_clearance: string;
  occurred_at: string;
  ip_address: string | null;
  outcome: "success" | "denied";
  detail: string | null;
}

/** Presentation only. More restricted reads as more urgent. */
export const CLASSIFICATION_TONE: Record<
  ClassificationCode,
  "neutral" | "medium" | "high" | "critical"
> = {
  unrestricted: "neutral",
  internal: "neutral",
  confidential: "high",
  restricted: "critical",
};

/**
 * A proportion rendered as text, always with its counts.
 *
 * Never returns a bare percentage. When the interval is too wide to be
 * informative the percentage is still shown — hiding it would be its own kind
 * of dishonesty — but it is shown inside the interval that qualifies it.
 */
export function describeProportion(p: Proportion): string {
  if (p.trials === 0) return "no outcomes yet";
  const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
  return `${p.successes} of ${p.trials} · ${pct(p.point)} (CI ${pct(p.ci_low)}–${pct(p.ci_high)})`;
}
