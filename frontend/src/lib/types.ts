import type { Aggregate } from "@/lib/aggregate";
import type { NodeAssessment } from "@/lib/assessment";

export interface GraphNode {
  id: string;
  uuid: string;
  label: string;
  name: string;
  /** ARGUS's own assessment, or null where it has none.
   *
   * Replaces `risk_score: number`, which carried the scenario generator's
   * planted value and defaulted to 0 — so an entity nobody had assessed was
   * indistinguishable from one assessed and found unremarkable. The optionality
   * is the point: every consumer now has to decide what to show when ARGUS has
   * no opinion. */
  assessment: NodeAssessment | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  properties: Record<string, any>;
  degree?: number;
  connections?: Record<string, number>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  properties: Record<string, any>;
}

export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type Severity = "Low" | "Medium" | "High" | "Critical";

export interface Incident {
  incident_id: string;
  type: string;
  severity: Severity;
  timestamp: string;
  description: string;
  status?: string;
  /** The storyline that planted this incident. Two alerts sharing one are
   * genuinely part of the same activity, which is what makes "related alerts"
   * a real link rather than a similarity heuristic. */
  storyline_id?: string | null;
  /** Human IDs of the entities this incident involves — used to relate an
   * alert to a case by intersecting with that case's evidence board. */
  involved_entity_ids?: string[];
  /** A bounded preview for display. Never a source for counts — see `spread`,
   * and `involved_coverage` for how much of the whole this represents. */
  involved_entities?: { label: string; properties: Record<string, unknown> }[];
  involved_coverage?: Aggregate<number>;
  /** Computed server-side across every involved entity, so it describes the
   * incident rather than whichever entities fit in the preview (audit B-04). */
  spread?: {
    involved_total: number;
    country_count: number;
    region_count: number;
    /** Bounded list for display; `country_count` is the authority. */
    countries: string[];
    regions: string[];
    /** Null when ARGUS has assessed none of the involved entities — which is a
     * different statement from "none of them scored". */
    peak_assessment_score: number | null;
    elevated_entities: number;
  };
}

export interface CaseSummary {
  case_id: string;
  title: string;
  status: "Draft" | "Open" | "UnderReview" | "Closed";
  priority: Severity;
  opened_at: string;
  closed_at?: string | null;
}

export interface CaseDetail extends CaseSummary {
  assigned_analyst: string;
  notes: string;
  linked_entities: { label: string; properties: Record<string, unknown> }[];
}

export interface DashboardSummary {
  total_persons: number;
  total_organizations: number;
  total_transactions: number;
  /** Entities ARGUS assessed as warranting review. Renamed from
   * `flagged_entities`, which counted entities the *generator* had marked. */
  elevated_entities: number;
  /** Investigations this deployment's users opened and have not concluded.
   *
   * Replaces `active_cases`, and the rename is not cosmetic: that figure
   * counted `Case` nodes, every one of which the scenario generator wrote from
   * a storyline it had just planted, complete with an invented analyst name.
   * The dashboard was reporting the answer key's size and calling it a
   * workload — the same defect Phase 7 removed from the alert queue. */
  open_investigations: number;
  investigations_by_state: Record<string, number>;
  investigation_outcomes: Record<string, number>;
  /** Case records written by a source, named for what they are. Kept, and no
   * longer presented as analyst work — the treatment Phase 7 gave `Incident`. */
  source_reported_cases: number;
  /** Alerts ARGUS raised and nobody has closed. Sourced from the alerting
   * tables since Phase 7; it previously counted open High/Critical `Incident`
   * nodes, which the scenario generator writes one of per storyline — so the
   * dashboard was reporting the answer key's size as the queue. */
  open_alerts: number;
  /** Open alerts in the top priority band. Counted across every alert, so it
   * may safely be stated in the same sentence as `open_alerts`. Deriving such a
   * figure from a display list capped it at that list's length (audit B-05). */
  high_priority_open_alerts: number;
  incidents_in_window: number;
  critical_incidents_in_window: number;
  window_days: number;
  /** Counts across every band, including `unassessed`, so they sum to the
   * population. There is deliberately no mean: an average over a population
   * ARGUS mostly could not assess summarises nothing. */
  assessment_distribution: { band: string; count: number }[];
  assessed_persons: number;
  /** Display list only — never a source for counts. */
  recent_incidents: Incident[];
  recent_source_reported_cases: CaseSummary[];
}

export interface TimelineItem {
  kind: "Event" | "Transaction" | "Communication";
  subtype: string;
  timestamp: string;
  details: Record<string, unknown>;
}
