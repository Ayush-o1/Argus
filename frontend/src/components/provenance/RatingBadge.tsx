import { cn } from "@/lib/cn";
import {
  CREDIBILITY_MEANING,
  RELIABILITY_MEANING,
  type CredibilityCode,
  type ReliabilityCode,
} from "@/lib/provenance";
import styles from "./provenance.module.css";

/**
 * An Admiralty rating, rendered as two cells rather than one.
 *
 * The seam between them is load-bearing. Source reliability and information
 * credibility answer different questions — "how much do we trust this source"
 * and "how well-supported is this particular claim" — and a reliable source can
 * report something uncorroborated just as an unreliable one can report
 * something confirmed elsewhere. Drawing them as one chip would invite reading
 * them as one score, which is precisely the collapse the backend refuses to
 * perform.
 *
 * There is no bar, no percentage and no colour ramp from good to bad, because
 * there is no scale: A→B is not the same distance as E→F, and nothing
 * establishes that it is.
 */
export function RatingBadge({
  reliability,
  credibility,
  className,
}: {
  reliability: ReliabilityCode;
  credibility: CredibilityCode;
  className?: string;
}) {
  const unjudged = reliability === "F" && credibility === "6";

  return (
    <span
      className={cn(styles.rating, className)}
      title={
        `Source reliability ${reliability} — ${RELIABILITY_MEANING[reliability]}\n` +
        `Information credibility ${credibility} — ${CREDIBILITY_MEANING[credibility]}\n\n` +
        "Admiralty Code (NATO STANAG 2511). Two independent readings; they are " +
        "never averaged into one figure."
      }
    >
      <span className={cn(styles.ratingAxis, toneFor(reliability, unjudged))}>{reliability}</span>
      <span className={cn(styles.ratingAxis, credibilityTone(credibility, unjudged))}>
        {credibility}
      </span>
    </span>
  );
}

function toneFor(reliability: ReliabilityCode, unjudged: boolean): string | undefined {
  if (unjudged) return styles.ratingUnjudged;
  if (reliability === "A" || reliability === "B") return styles.ratingStrong;
  if (reliability === "D" || reliability === "E") return styles.ratingWeak;
  return undefined;
}

function credibilityTone(credibility: CredibilityCode, unjudged: boolean): string | undefined {
  if (unjudged) return styles.ratingUnjudged;
  if (credibility === "1" || credibility === "2") return styles.ratingStrong;
  if (credibility === "4" || credibility === "5") return styles.ratingWeak;
  return undefined;
}

/** The reliability of a source on its own, where no specific claim is in view —
 * a source registry row, or the header of a list of that source's reports. */
export function SourceReliabilityBadge({
  reliability,
  className,
}: {
  reliability: ReliabilityCode;
  className?: string;
}) {
  return (
    <span
      className={cn(styles.rating, className)}
      title={`Source reliability ${reliability} — ${RELIABILITY_MEANING[reliability]}`}
    >
      <span className={cn(styles.ratingAxis, toneFor(reliability, reliability === "F"))}>
        {reliability}
      </span>
    </span>
  );
}
