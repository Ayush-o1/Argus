import {
  AlertTriangle,
  BarChart3,
  Clock,
  FlaskConical,
  GitMerge,
  LayoutGrid,
  Map,
  Radio,
  Search,
  Settings,
  ShieldHalf,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badgeKey?: "alerts" | "cases";
  /** One-line purpose, surfaced as the nav tooltip (and the only affordance
   * when the sidebar is collapsed to icons). */
  hint?: string;
  /** Permission required to use this surface. Items the signed-in role lacks
   * are hidden — an affordance, not a control: the server enforces the same
   * permission again, because a hidden link is not a boundary. */
  permission?: string;
}

export interface NavGroup {
  title?: string;
  items: NavItem[];
}

/** Grouped by where each surface sits in the investigator's actual loop —
 * triage what was flagged, investigate it across graph/geography/time, then
 * step back and analyze patterns. The previous grouping mixed entry points
 * (Search) with analysis surfaces (Graph, Map) and filed Analytics under
 * "Investigation", which told a new user nothing about where to start. */
export const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutGrid, hint: "Situational overview",  permission: "entity:read",}],
  },
  {
    title: "Triage",
    items: [
      { label: "Alerts", href: "/alerts", icon: AlertTriangle, badgeKey: "alerts", hint: "Flagged anomalies awaiting review",  permission: "alert:read",},
      { label: "Cases", href: "/cases", icon: ShieldHalf, badgeKey: "cases", hint: "Active investigations",  permission: "case:read",},
    ],
  },
  {
    title: "Investigate",
    items: [
      { label: "Search", href: "/search", icon: Search, hint: "Find any entity in the graph",  permission: "entity:read",},
      { label: "Graph Explorer", href: "/graph", icon: Waypoints, hint: "Explore entity relationships",  permission: "graph:read",},
      { label: "Map", href: "/map", icon: Map, hint: "Geographic and route intelligence",  permission: "graph:read",},
      { label: "Timeline", href: "/timeline", icon: Clock, hint: "Temporal activity patterns",  permission: "entity:read",},
    ],
  },
  {
    title: "Analyze",
    items: [{ label: "Analytics", href: "/analytics", icon: BarChart3, hint: "Graph algorithms and anomaly detection",  permission: "analytics:read",}],
  },
  {
    title: "System",
    items: [
      { label: "Sources", href: "/sources", icon: Radio, hint: "Feed health, freshness and rejected records",  permission: "ingest:read",},
      { label: "Resolution", href: "/resolution", icon: GitMerge, hint: "Records ARGUS believes describe the same entity",  permission: "resolution:read",},
      { label: "Scenario Generator", href: "/scenario", icon: FlaskConical, hint: "Inject a synthetic storyline",  permission: "scenario:generate",},
      { label: "Settings", href: "/settings", icon: Settings, hint: "Instance configuration" },
    ],
  },
];
