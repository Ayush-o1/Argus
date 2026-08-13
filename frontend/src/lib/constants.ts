import {
  AlertTriangle,
  BarChart3,
  Clock,
  FlaskConical,
  LayoutGrid,
  Map,
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
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutGrid, hint: "Situational overview" }],
  },
  {
    title: "Triage",
    items: [
      { label: "Alerts", href: "/alerts", icon: AlertTriangle, badgeKey: "alerts", hint: "Flagged anomalies awaiting review" },
      { label: "Cases", href: "/cases", icon: ShieldHalf, badgeKey: "cases", hint: "Active investigations" },
    ],
  },
  {
    title: "Investigate",
    items: [
      { label: "Search", href: "/search", icon: Search, hint: "Find any entity in the graph" },
      { label: "Graph Explorer", href: "/graph", icon: Waypoints, hint: "Explore entity relationships" },
      { label: "Map", href: "/map", icon: Map, hint: "Geographic and route intelligence" },
      { label: "Timeline", href: "/timeline", icon: Clock, hint: "Temporal activity patterns" },
    ],
  },
  {
    title: "Analyze",
    items: [{ label: "Analytics", href: "/analytics", icon: BarChart3, hint: "Graph algorithms and anomaly detection" }],
  },
  {
    title: "System",
    items: [
      { label: "Scenario Generator", href: "/scenario", icon: FlaskConical, hint: "Inject a synthetic storyline" },
      { label: "Settings", href: "/settings", icon: Settings, hint: "Instance configuration" },
    ],
  },
];
