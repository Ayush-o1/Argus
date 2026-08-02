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
  badgeKey?: "alerts";
}

export interface NavGroup {
  title?: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutGrid },
      { label: "Graph Explorer", href: "/graph", icon: Waypoints },
      { label: "Search", href: "/search", icon: Search },
      { label: "Map", href: "/map", icon: Map },
      { label: "Timeline", href: "/timeline", icon: Clock },
    ],
  },
  {
    title: "Investigation",
    items: [
      { label: "Cases", href: "/cases", icon: ShieldHalf },
      { label: "Alerts", href: "/alerts", icon: AlertTriangle, badgeKey: "alerts" },
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
    ],
  },
  {
    title: "Tools",
    items: [{ label: "Scenario Generator", href: "/scenario", icon: FlaskConical }],
  },
  {
    items: [{ label: "Settings", href: "/settings", icon: Settings }],
  },
];
