import type { Aggregate } from "@/lib/aggregate";

export interface GraphNode {
  id: string;
  uuid: string;
  label: string;
  name: string;
  risk_score: number;
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
    peak_risk: number | null;
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
  flagged_entities: number;
  active_cases: number;
  open_alerts: number;
  /** Counted across every incident, so it may safely be stated in the same
   * sentence as `open_alerts`. Deriving it from `recent_incidents` capped it at
   * that list's length and understated it (audit B-05). */
  critical_open_alerts: number;
  incidents_in_window: number;
  critical_incidents_in_window: number;
  window_days: number;
  avg_risk_score: number;
  risk_distribution: { level: Severity; count: number }[];
  /** Display list only — never a source for counts. */
  recent_incidents: Incident[];
  recent_cases: CaseSummary[];
}

export interface TimelineItem {
  kind: "Event" | "Transaction" | "Communication";
  subtype: string;
  timestamp: string;
  details: Record<string, unknown>;
}
