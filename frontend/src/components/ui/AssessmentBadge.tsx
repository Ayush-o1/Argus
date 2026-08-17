import { Badge } from "./Badge";
import {
  BAND_SHORT,
  BAND_TONE,
  formatCoverage,
  formatScore,
  type AssessmentBand,
  type NodeAssessment,
} from "@/lib/assessment";

/**
 * ARGUS's assessment of one entity, rendered so it cannot be mistaken for a
 * verdict.
 *
 * Two rules, both load-bearing:
 *
 *   The score never appears without the share of the model behind it. They are
 *   printed by the same component so no surface can show one and omit the
 *   other.
 *
 *   An unassessed entity renders as "Not assessed", never as a quiet zero. The
 *   badge this replaced took `risk_score: number`, so an entity nobody had
 *   examined arrived as 0 and was drawn identically to one examined and found
 *   clean.
 */
export function AssessmentBadge({
  assessment,
  showScore = true,
}: {
  assessment: NodeAssessment | null | undefined;
  showScore?: boolean;
}) {
  if (!assessment) {
    return (
      <Badge tone="neutral" title="ARGUS has published no assessment for this entity.">
        Not assessed
      </Badge>
    );
  }

  const band = assessment.band as AssessmentBand;
  const score = formatScore(assessment.score);
  const coverage = formatCoverage(assessment.coverage);
  const label = BAND_SHORT[band] ?? band;

  const title =
    score === null
      ? `Too little evidence to score — ${coverage ?? "an unknown share"} of the model could be evaluated.`
      : `Score ${score} of 100, over the ${coverage ?? "unknown"} of the model that could be evaluated.`;

  return (
    <Badge tone={BAND_TONE[band] ?? "neutral"} title={title}>
      {label}
      {showScore && score !== null ? ` · ${score}` : null}
    </Badge>
  );
}
