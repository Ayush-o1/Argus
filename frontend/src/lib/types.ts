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
  involved_entities?: { label: string; properties: Record<string, unknown> }[];
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
  avg_risk_score: number;
  risk_distribution: { level: Severity; count: number }[];
  recent_incidents: Incident[];
  recent_cases: CaseSummary[];
}

export interface TimelineItem {
  kind: "Event" | "Transaction" | "Communication";
  subtype: string;
  timestamp: string;
  details: Record<string, unknown>;
}
