import { BAND_TONE, type AssessmentBand, type BandTone } from "@/lib/assessment";

export function formatAgo(iso: string): string {
  const hours = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 3_600_000));
  if (hours < 1) return "<1h";
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

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
