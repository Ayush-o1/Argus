import { BAND_TONE, type AssessmentBand, type BandTone } from "@/lib/assessment";

/** Fixed "now" for the fixture phase, matching the fixture data's own
 * anchor date (`nextFixtureModel.last_run_at`) — so "ago" labels stay stable
 * across reloads instead of drifting against the real clock while every
 * other figure on screen is frozen at 2026-08-24. Becomes `Date.now()` once
 * Phase 12 swaps in live data. */
const FIXTURE_NOW = Date.parse("2026-08-24T16:00:00Z");

export function formatAgo(iso: string): string {
  const hours = Math.max(0, Math.round((FIXTURE_NOW - Date.parse(iso)) / 3_600_000));
  if (hours < 1) return "<1h";
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

/** Points of divergence between ARGUS's score and an analyst's before the UI
 * treats it as disagreement rather than noise. Matches the Claude Design
 * prototype's `divergenceThreshold` default; not yet user-configurable. */
export const DIVERGENCE_THRESHOLD = 15;

const TONE_VAR: Record<BandTone, string> = {
  critical: "var(--risk-critical)",
  high: "var(--risk-high)",
  medium: "var(--risk-medium)",
  low: "var(--risk-low)",
  neutral: "var(--risk-unknown)",
};

/** The color an assessment band renders as, reusing the real `BAND_TONE`
 * mapping (`lib/assessment.ts`) and the existing risk CSS variables —
 * `insufficient_evidence` stays the neutral "unknown" grey, never a calm
 * green, for the same reason `assessmentTier()` in `lib/theme.ts` refuses to
 * treat "no finding" and "no evidence" as the same thing. */
export function bandColorVar(band: AssessmentBand | null | undefined): string {
  if (!band) return TONE_VAR.neutral;
  return TONE_VAR[BAND_TONE[band]];
}

export function severityColorVar(severity: string): string {
  return severity === "Critical" ? "var(--risk-critical)" : severity === "High" ? "var(--risk-high)" : "var(--risk-medium)";
}
