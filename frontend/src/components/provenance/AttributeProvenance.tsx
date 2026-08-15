"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";
import {
  KIND_MEANING,
  describeValue,
  formatTimestamp,
  type AttributeProvenance as AttributeProvenanceData,
} from "@/lib/provenance";
import { KindBadge, SyntheticBadge } from "./KindBadge";
import { RatingBadge, SourceReliabilityBadge } from "./RatingBadge";
import styles from "./provenance.module.css";

/**
 * The provenance affordance on a single displayed value.
 *
 * One click from any fact to where it came from, when ARGUS learned it, and how
 * good the source is. Collapsed by default — provenance that shouts at every
 * row is provenance that gets ignored — but never more than one interaction
 * away, and the kind badge is always visible so the analyst can see *what sort
 * of claim* they are reading without opening anything.
 *
 * When there is no provenance at all, this says so rather than rendering
 * nothing: silence would be indistinguishable from a well-sourced value.
 */
export function AttributeProvenance({
  label,
  value,
  provenance,
  complete = true,
}: {
  label: string;
  value: unknown;
  provenance: AttributeProvenanceData | undefined;
  /** Whether the resolution behind `provenance` read every observation for this
   * entity. False turns "unsourced" into "not found in what was read", which is
   * a materially weaker and more accurate claim. */
  complete?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const kind = provenance?.kind ?? "unattributed";
  const observations = provenance?.observations ?? [];
  const assertions = provenance?.assertions ?? [];
  const synthetic =
    observations.some((o) => o.source_is_synthetic) ||
    assertions.some((a) => a.evidence.some((e) => e.source_is_synthetic));

  return (
    <div>
      <button
        type="button"
        className={styles.attributeTrigger}
        onClick={() => setOpen((previous) => !previous)}
        aria-expanded={open}
        aria-label={`Provenance for ${label}`}
      >
        <ChevronRight
          size={12}
          className={cn(styles.attributeChevron, open && styles.attributeChevronOpen)}
        />
        <KindBadge kind={kind} />
        {synthetic ? <SyntheticBadge /> : null}
      </button>

      {open ? (
        <div className={styles.attributeDetail}>
          <p className={styles.detailMeaning}>{KIND_MEANING[kind]}</p>

          {observations.length === 0 && assertions.length === 0 ? (
            <p className={styles.detailNote}>
              {complete
                ? "Nothing in the provenance store accounts for this value. It may predate " +
                  "the provenance layer or have been written directly to the graph. Treat it " +
                  "as unsourced."
                : "No source for this value was found in the observations read — but not all " +
                  "of this entity's observations were read, so it may be accounted for by one " +
                  "that was not. Not the same as unsourced, and not claimed as such."}
            </p>
          ) : null}

          {assertions.length > 0 ? (
            <div className={styles.detailList}>
              {assertions.map((assertion) => (
                <div key={assertion.assertion_id} className={styles.detailRow}>
                  <span className={styles.detailLabel}>Asserted</span>
                  <span className={styles.detailValue}>
                    {describeValue(assertion.object_value)}
                  </span>
                  <RatingBadge
                    reliability={assertion.rating.reliability}
                    credibility={assertion.rating.credibility}
                  />
                  <span className={styles.detailNote} style={{ flexBasis: "100%", margin: 0 }}>
                    {assertion.method} · by {assertion.asserted_by_display} ·{" "}
                    {formatTimestamp(assertion.asserted_at)}
                    {assertion.corroboration
                      ? ` · ${assertion.corroboration.independent_sources} independent source${
                          assertion.corroboration.independent_sources === 1 ? "" : "s"
                        }`
                      : null}
                  </span>
                  {assertion.note ? (
                    <span className={styles.detailNote} style={{ flexBasis: "100%" }}>
                      {assertion.note}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          {observations.length > 0 ? (
            <div className={styles.detailList} style={{ marginTop: assertions.length ? 12 : 0 }}>
              {observations.map((observation) => (
                <div key={observation.observation_id} className={styles.detailRow}>
                  <span className={styles.detailLabel}>Reported by</span>
                  <span className={styles.detailValue}>{observation.source_name}</span>
                  {/* Reliability alone. An observation is what a source said;
                      credibility is a judgement about a *claim*, and nobody has
                      made one here. Rendering a second character would invent a
                      rating that does not exist. */}
                  <SourceReliabilityBadge reliability={observation.source_reliability} />
                  {observation.source_is_synthetic ? <SyntheticBadge /> : null}

                  <span className={styles.detailNote} style={{ flexBasis: "100%", margin: 0 }}>
                    Reported value: <span className={styles.mono}>
                      {describeValue(observation.reported_value)}
                    </span>
                    {!observation.matches_current_value ? (
                      <>
                        {" "}
                        — differs from the stored value{" "}
                        <span className={styles.mono}>{describeValue(value)}</span>, so
                        something changed it after it was reported.
                      </>
                    ) : null}
                  </span>
                  <span className={styles.detailNote} style={{ flexBasis: "100%", margin: 0 }}>
                    ARGUS learned this {formatTimestamp(observation.recorded_at)} · collected{" "}
                    {formatTimestamp(observation.collected_at)} · occurred{" "}
                    {formatTimestamp(observation.occurred_at)}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
