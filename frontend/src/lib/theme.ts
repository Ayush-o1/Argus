/**
 * Single source of truth for color values that must be readable from plain
 * JS/TS (Cytoscape stylesheets, recharts/visx SVG props, canvas-based map
 * layers) where a CSS custom property can't be used directly. These values
 * MUST stay in sync with the semantic tokens in styles/tokens.css — if you
 * change a color here, change it there too, and vice versa.
 */

export const RISK_COLORS = {
  Critical: "#FF3B47",
  High: "#FF7D1A",
  Medium: "#FFB800",
  Low: "#1AE87B",
} as const;

export const RISK_COLOR_UNKNOWN = "#8892A4";

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
