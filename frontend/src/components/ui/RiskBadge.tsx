import { Badge } from "./Badge";

export type RiskLevel = "critical" | "high" | "medium" | "low" | "unknown";

const LABELS: Record<RiskLevel, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  unknown: "Unknown",
};

/** Maps a 0–100 risk score to a discrete severity level, per ARGUS_PLAN.md Phase 7. */
export function riskLevelFromScore(score: number): RiskLevel {
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 35) return "medium";
  if (score >= 0) return "low";
  return "unknown";
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  const tone = level === "unknown" ? "neutral" : level;
  return <Badge tone={tone}>{LABELS[level]}</Badge>;
}
