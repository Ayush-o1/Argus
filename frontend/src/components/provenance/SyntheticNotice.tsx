"use client";

import { Beaker } from "lucide-react";
import { useProvenanceSummary, useSources } from "@/hooks/useProvenance";
import styles from "./provenance.module.css";

/**
 * States plainly that the data on screen was fabricated.
 *
 * The audit's sharpest finding was that ARGUS's scenario generator plants
 * storylines and marks their participants high-risk, and every surface then
 * renders those planted values with the authority of analytic conclusions — so
 * every "discovery" succeeds by construction and demonstrates nothing.
 *
 * This banner is driven by the source registry, not by a build flag or a
 * hardcoded string. It appears because a registered source has `is_synthetic`
 * set, and it will disappear on its own the day real sources replace it —
 * without anybody remembering to remove it, which is the failure mode a
 * hardcoded notice eventually has.
 */
export function SyntheticNotice() {
  const { data: summary } = useProvenanceSummary();
  const { data: sources } = useSources();

  if (!summary?.has_synthetic_data) return null;

  const synthetic = (sources ?? []).filter((source) => source.is_synthetic);
  const names = synthetic.map((source) => source.name).join(", ");
  const observations = summary.counts.observations ?? 0;

  return (
    <div className={styles.syntheticNotice}>
      <Beaker size={16} color="#f472b6" style={{ flexShrink: 0, marginTop: 2 }} />
      <div className={styles.syntheticNoticeBody}>
        <strong>Synthetic data.</strong> {observations.toLocaleString()} of the records behind
        these surfaces were produced by {names || "a synthetic source"}, which fabricates its
        content rather than reporting on anything that happened. Ratings, risk values and
        relationships here demonstrate how ARGUS presents intelligence — they are not
        intelligence. Every value carries its source, one click away.
      </div>
    </div>
  );
}
