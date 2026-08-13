/**
 * Single source of truth for color values that must be readable from plain
 * JS/TS (Cytoscape stylesheets, recharts/visx SVG props, canvas-based map
 * layers) where a CSS custom property can't be used directly. These values
 * MUST stay in sync with the semantic tokens in styles/tokens.css — if you
 * change a color here, change it there too, and vice versa.
 */

/** Monotonic in salience — see the risk block in styles/tokens.css for why
 * "Low" is deliberately a quiet slate rather than a saturated green. */
export const RISK_COLORS = {
  Critical: "#FF3B47",
  High: "#FF7D1A",
  Medium: "#E0A800",
  Low: "#64748B",
} as const;

export const RISK_COLOR_UNKNOWN = "#8892A4";

/** Positive confirmation only (resolved/cleared/healthy) — never "low risk". */
export const STATUS_OK = "#22C55E";

export const ENTITY_COLORS = {
  Person: "#3D7BFF",
  Organization: "#A855F7",
  Location: "#1AE87B",
  Vehicle: "#FFB800",
  Device: "#06B6D4",
  Account: "#F97316",
  Event: "#EC4899",
  Document: "#84CC16",
  Shipment: "#F43F5E",
} as const;

export type EntityColorKey = keyof typeof ENTITY_COLORS;

export type RiskTier = "critical" | "high" | "medium" | "low" | "none";

/** Independent of entity-type fill color, so risk reads as its own visual
 * channel — a critical Person and a critical Organization should look
 * equally alarming without their type color competing for attention. Shared
 * between the Graph Explorer and the Map, which both encode risk this way. */
export function riskTier(riskScore: number): RiskTier {
  if (riskScore >= 80) return "critical";
  if (riskScore >= 60) return "high";
  if (riskScore >= 35) return "medium";
  if (riskScore > 0) return "low";
  return "none";
}
