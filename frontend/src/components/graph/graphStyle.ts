import type { StylesheetJson } from "cytoscape";
import { ENTITY_COLORS, RISK_COLORS, RISK_COLOR_UNKNOWN, type RiskTier } from "@/lib/theme";

const NODE_COLORS: Record<string, string> = {
  ...ENTITY_COLORS,
  Case: ENTITY_COLORS.Person,
  Incident: RISK_COLORS.High,
  Storyline: RISK_COLOR_UNKNOWN,
};

const EDGE_COLORS: Record<string, string> = {
  TRANSACTED_WITH: "#F97316",
  COMMUNICATED_WITH: "#06B6D4",
  DIRECTS: "#A855F7",
  CONTROLS: "#FF3B47",
  EMPLOYED_BY: "#8892A4",
  OWNS_ACCOUNT: "#5A6478",
  OWNS_DEVICE: "#5A6478",
  OWNS_VEHICLE: "#5A6478",
  SHARES_DEVICE: "#FF7D1A",
  ATTENDED: "#EC4899",
  OCCURRED_AT: "#5A6478",
  ISSUED_TO: "#84CC16",
  ISSUED_BY: "#84CC16",
  INVOLVES: "#FF3B47",
  LINKED_TO: "#3D7BFF",
};

const RING_COLOR: Record<RiskTier, string> = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: "#2b3245",
  none: "#2b3245",
};

const RING_WIDTH: Record<RiskTier, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 2,
  none: 2,
};

// Correlation-link edges (the `/next` Investigate Graph lens's fixture data —
// see `lib/next/fixtures.ts`'s `nextFixtureGraphEdges` — set `type` to the
// correlation tier itself: "established" | "probable" | "possible", matching
// `TIER_ESTABLISHED`/`TIER_PROBABLE`/`TIER_POSSIBLE` in
// `backend/app/correlation/model.py`) render as line style, not just color,
// so the distinction survives a screenshot or colorblind viewing. Unrelated
// relationship types (TRANSACTED_WITH etc., in EDGE_COLORS above) never
// collide with these three selector values.
const CORRELATION_TIER_STYLE: Record<
  "established" | "probable" | "possible",
  { color: string; lineStyle: "solid" | "dashed" | "dotted"; width: number }
> = {
  established: { color: "#3D7BFF", lineStyle: "solid", width: 2 },
  probable: { color: "#8892A4", lineStyle: "solid", width: 1.1 },
  possible: { color: "#5A6478", lineStyle: "dashed", width: 1 },
};

export function buildGraphStylesheet(): StylesheetJson {
  const nodeColorRules = Object.entries(NODE_COLORS).map(([label, color]) => ({
    selector: `node[entityLabel = "${label}"]`,
    style: { "background-color": color },
  }));

  const edgeColorRules = Object.entries(EDGE_COLORS).map(([type, color]) => ({
    selector: `edge[relType = "${type}"]`,
    style: { "line-color": color, "target-arrow-color": color },
  }));

  const riskRingRules = (Object.keys(RING_COLOR) as RiskTier[]).map((tier) => ({
    selector: `node[riskTier = "${tier}"]`,
    style: { "border-color": RING_COLOR[tier], "border-width": RING_WIDTH[tier] },
  }));

  const correlationTierRules = (
    Object.keys(CORRELATION_TIER_STYLE) as (keyof typeof CORRELATION_TIER_STYLE)[]
  ).map((tier) => {
    const s = CORRELATION_TIER_STYLE[tier];
    return {
      selector: `edge[relType = "${tier}"]`,
      style: {
        "line-color": s.color,
        "target-arrow-color": s.color,
        "line-style": s.lineStyle,
        width: s.width,
      },
    };
  });

  return [
    {
      selector: "node",
      style: {
        "background-color": "#8892A4",
        label: "data(displayLabel)",
        color: "#F0F2F7",
        "font-size": 10,
        "font-family": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
        "font-weight": 500,
        "text-valign": "bottom",
        "text-margin-y": 5,
        width: "data(size)",
        height: "data(size)",
        "border-width": 2,
        "border-color": "#2b3245",
        "border-opacity": 1,
        "text-outline-width": 2,
        "text-outline-color": "#0B0C0F",
        "transition-property": "border-width, border-color, opacity",
        "transition-duration": 120,
      },
    },
    ...nodeColorRules,
    ...riskRingRules,
    {
      selector: "node:selected",
      style: {
        "border-width": 4,
        "border-color": "#F0F2F7",
      },
    },
    {
      selector: "node.faded",
      style: { opacity: 0.12, "text-opacity": 0 },
    },
    {
      selector: "node.highlighted",
      style: { "border-color": "#F0F2F7", "border-width": 4 },
    },
    {
      // Zoom/importance-driven label thinning — text-opacity is toggled from
      // GraphCanvas rather than expressed declaratively here, since Cytoscape
      // stylesheets can't branch on the live zoom level.
      selector: "node.label-hidden",
      style: { "text-opacity": 0 },
    },
    {
      selector: "edge",
      style: {
        width: 1.1,
        "line-color": "#252B3B",
        "target-arrow-color": "#252B3B",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.6,
        "curve-style": "bezier",
        opacity: 0.55,
        "transition-property": "opacity, width",
        "transition-duration": 120,
      },
    },
    ...edgeColorRules,
    ...correlationTierRules,
    {
      selector: "edge.faded",
      style: { opacity: 0.04 },
    },
    {
      selector: "edge.highlighted",
      style: { "line-color": "#3D7BFF", "target-arrow-color": "#3D7BFF", opacity: 1, width: 2.25 },
    },
    {
      selector: "edge.edge-selected",
      style: { "line-color": "#F0F2F7", "target-arrow-color": "#F0F2F7", opacity: 1, width: 2.5 },
    },
    {
      // Used by the type/risk filters and Focus mode — keeps hidden
      // nodes/edges in the Cytoscape instance (so re-showing them is instant,
      // no re-fetch) rather than removing elements outright.
      selector: ".hidden",
      style: { display: "none" },
    },
  ] as StylesheetJson;
}

export function nodeSize(riskScore: number): number {
  return 16 + Math.min(riskScore, 100) * 0.2;
}
