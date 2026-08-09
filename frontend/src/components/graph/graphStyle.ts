import type { StylesheetJson } from "cytoscape";
import { ENTITY_COLORS, RISK_COLORS, RISK_COLOR_UNKNOWN } from "@/lib/theme";

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

export function buildGraphStylesheet(): StylesheetJson {
  const nodeColorRules = Object.entries(NODE_COLORS).map(([label, color]) => ({
    selector: `node[entityLabel = "${label}"]`,
    style: { "background-color": color },
  }));

  const edgeColorRules = Object.entries(EDGE_COLORS).map(([type, color]) => ({
    selector: `edge[relType = "${type}"]`,
    style: { "line-color": color, "target-arrow-color": color },
  }));

  return [
    {
      selector: "node",
      style: {
        "background-color": "#8892A4",
        label: "data(label)",
        color: "#F0F2F7",
        "font-size": 9,
        "font-family": "var(--font-sans)",
        "text-valign": "bottom",
        "text-margin-y": 4,
        width: "data(size)",
        height: "data(size)",
        "border-width": 2,
        "border-color": "#0B0C0F",
        "text-outline-width": 2,
        "text-outline-color": "#0B0C0F",
      },
    },
    ...nodeColorRules,
    {
      selector: "node:selected",
      style: {
        "border-width": 3,
        "border-color": "#F0F2F7",
      },
    },
    {
      selector: "node.faded",
      style: { opacity: 0.15 },
    },
    {
      selector: "node.highlighted",
      style: { "border-width": 3, "border-color": "#3D7BFF" },
    },
    {
      selector: "edge",
      style: {
        width: 1.2,
        "line-color": "#252B3B",
        "target-arrow-color": "#252B3B",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.6,
        "curve-style": "bezier",
        opacity: 0.7,
      },
    },
    ...edgeColorRules,
    {
      selector: "edge.faded",
      style: { opacity: 0.05 },
    },
    {
      selector: "edge.highlighted",
      style: { "line-color": "#3D7BFF", "target-arrow-color": "#3D7BFF", opacity: 1, width: 2 },
    },
    {
      // Used by the legend's type filter — keeps hidden nodes/edges in the
      // Cytoscape instance (so re-showing them is instant, no re-fetch) rather
      // than removing elements outright.
      selector: ".hidden",
      style: { display: "none" },
    },
  ] as StylesheetJson;
}

export function nodeSize(riskScore: number): number {
  return 18 + Math.min(riskScore, 100) * 0.18;
}
