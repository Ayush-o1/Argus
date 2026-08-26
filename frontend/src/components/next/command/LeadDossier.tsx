"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAnalystAssessments } from "@/hooks/useInvestigations";
import { useAssessmentModel, useSubjectAssessment } from "@/hooks/useAssessment";
import { BAND_LABEL, type AssessmentBand } from "@/lib/assessment";
import type { GraphNode } from "@/lib/types";
import { bandColorVar } from "@/lib/next/format";
import { NEXT_MODE_PATH } from "@/lib/next/modeRouting";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./LeadDossier.module.css";

/**
 * The assessment dossier for whatever subject is selected — the design's
 * centrepiece: ARGUS's score and an analyst's, kept as two independent
 * readings, never merged into a single number. This rule is absolute across
 * the whole product (see `assessmentTier()` in `lib/theme.ts`), not a style
 * choice specific to this screen.
 *
 * Fully live (Phase 12, second pass): the per-signal breakdown comes from
 * `useSubjectAssessment` (`/api/assessment/subject/{ref}`) — its `signals`
 * are exactly `SignalOutcome` (`evaluable`, `magnitude`, `contribution`),
 * the same shape the fixture modelled, confirmed live rather than assumed.
 * The analyst side comes from `useAnalystAssessments`, whose real
 * `AnalystAssessment` carries an `analyst_band` and a `dissents: boolean |
 * null` — no numeric score. Plotting that on the same 0-100 axis as ARGUS's
 * score would fabricate a position, so the axis keeps only ARGUS's real
 * marker; the analyst reading is shown as a band-vs-band comparison instead,
 * driven by the backend's own `dissents` verdict rather than a recomputed
 * divergence threshold.
 */
export function LeadDossier({ subject }: { subject: GraphNode }) {
  const router = useRouter();
  const pins = useNextScopeStore((s) => s.pins);
  const togglePin = useNextScopeStore((s) => s.togglePin);
  const setLens = useNextScopeStore((s) => s.setLens);
  const setFocus = useNextScopeStore((s) => s.setFocus);

  const assessment = subject.assessment;
  const { data: subjectAssessment, isLoading: signalsLoading } = useSubjectAssessment(subject.id);
  const { data: analystMap } = useAnalystAssessments([subject.id]);
  const { data: assessmentModel } = useAssessmentModel();

  const signalTitleMap = useMemo(
    () => new Map((assessmentModel?.signals ?? []).map((s) => [s.signal_id, s.title])),
    [assessmentModel],
  );
  const signalTitle = (signalId: string): string | undefined => signalTitleMap.get(signalId);

  const assessments = analystMap?.[subject.id] ?? [];
  const analyst = assessments.length
    ? [...assessments].sort((a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at))[0]
    : null;

  const signals = subjectAssessment?.signals ?? [];
  const fired = signals.filter((s) => s.evaluable && (s.magnitude ?? 0) > 0);
  const notEvaluable = signals.filter((s) => !s.evaluable);

  const argusScore = assessment?.score ?? null;
  const argusX = argusScore ?? 0;
  const showTension = analyst?.dissents === true;
  const coverage = assessment?.coverage ?? 0;
  const coverPct = Math.round(coverage * 100);
  const bandColor = bandColorVar(assessment?.band);
  const analystBandColor = analyst ? bandColorVar(analyst.analyst_band as AssessmentBand) : null;

  const isPinned = pins.includes(subject.id);
  const place = [subject.properties.city, subject.properties.country].filter(Boolean).join(", ");

  return (
    <section className={styles.section} aria-label="Lead dossier">
      <div className={styles.head}>
        <span className={styles.headIcon}>
          <EntityTypeIcon label={subject.label} size={18} />
        </span>
        <div className={styles.headText}>
          <h2 className={styles.name}>{subject.name}</h2>
          <p className={styles.meta}>
            {subject.id} · {subject.label} · {place} · {subject.properties.region}
          </p>
        </div>
        <button type="button" className={styles.pinButton} onClick={() => togglePin(subject.id)}>
          {isPinned ? "PINNED" : "PIN TO WORKING SET"}
        </button>
        <button
          type="button"
          className={styles.investigateButton}
          onClick={() => {
            setLens("graph");
            setFocus(subject.id);
            router.push(NEXT_MODE_PATH.investigate);
          }}
        >
          OPEN IN INVESTIGATE
        </button>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHead}>
          <span className={styles.cardTitle}>ASSESSMENT</span>
          <span className={styles.cardHeadSpacer} />
          <span
            className={styles.stateBadge}
            style={{
              color: showTension ? "var(--tension)" : analyst ? "var(--text-code)" : "var(--text-secondary)",
              borderColor: showTension ? "var(--tension)" : analyst ? "rgba(61,123,255,0.5)" : "var(--surface-border)",
              background: showTension ? "rgba(199,122,181,0.08)" : "transparent",
            }}
          >
            {showTension
              ? "MACHINE AND ANALYST DISAGREE"
              : analyst?.dissents === false
                ? "CORROBORATED BY ANALYST"
                : analyst
                  ? "REVIEWED BEFORE ARGUS ASSESSED THIS SUBJECT"
                  : "UNREVIEWED BY ANALYST"}
          </span>
        </div>

        <div className={styles.gaugesGrid}>
          <div className={styles.gaugeCol}>
            <div className={styles.gaugeLabel}>ARGUS ASSESSMENT</div>
            <div className={styles.scoreRow}>
              <span className={styles.scoreValue} style={{ color: bandColor }}>
                {argusScore ?? "—"}
              </span>
              <span className={styles.scoreDenominator}>/100</span>
            </div>
            <div className={styles.bandLabel}>{assessment ? BAND_LABEL[assessment.band] : "Not assessed"}</div>
            <div className={styles.subLabel}>
              over {coverPct}% of the model · {fired.length} signal{fired.length === 1 ? "" : "s"} fired
            </div>
          </div>
          <div className={styles.gaugeCol}>
            <div className={styles.gaugeLabel}>ANALYST JUDGMENT</div>
            {analyst ? (
              <>
                <div className={styles.scoreRow}>
                  <span className={styles.analystBandValue} style={{ color: analystBandColor ?? undefined }}>
                    {BAND_LABEL[analyst.analyst_band as AssessmentBand] ?? analyst.analyst_band}
                  </span>
                </div>
                <div className={styles.bandLabel}>{analyst.confidence} confidence</div>
                <div className={styles.subLabel}>
                  {analyst.author_username} · {new Date(analyst.recorded_at).toLocaleString()}
                </div>
              </>
            ) : (
              <>
                <div className={styles.scoreDash}>—</div>
                <div className={styles.noAnalystNote}>Not yet assessed by an analyst</div>
                <div className={styles.subLabel}>ARGUS&apos;s view stands alone. Nothing has corroborated or contradicted it.</div>
              </>
            )}
          </div>
        </div>

        <div className={styles.axisWrap}>
          <div className={styles.axis}>
            <span className={styles.axisLine} />
            <span className={styles.axisTick} style={{ left: 0 }}>
              0
            </span>
            <span className={styles.axisTick} style={{ right: 0 }}>
              100
            </span>
            <span
              className={styles.coverBand}
              style={{ left: `${Math.max(0, argusX - (100 - coverPct) / 2)}%`, width: `${Math.max(5, 100 - coverPct)}%` }}
              title={`Uncertainty band — ${100 - coverPct}% of the model could not be evaluated`}
            />
            <span className={styles.marker} style={{ left: `${argusX}%`, background: bandColor }} />
            <span className={styles.markerLabel} style={{ left: `${argusX}%`, color: bandColor }}>
              ARGUS
            </span>
          </div>
          {/* No numeric position exists for the analyst's reading — `AnalystAssessment`
              carries a band, not a score — so it is never plotted on this axis. A
              band-vs-band comparison, driven by the backend's own `dissents` verdict,
              says the same thing honestly instead of inventing a coordinate. */}
          {analyst ? (
            <div className={styles.bandCompareRow}>
              <span className={styles.bandChip} style={{ borderColor: bandColor }}>
                <span className={styles.bandChipLabel}>ARGUS</span>
                <span style={{ color: bandColor }}>{assessment ? BAND_LABEL[assessment.band] : "—"}</span>
              </span>
              <span className={styles.dissentGlyph}>{showTension ? "≠" : analyst.dissents === false ? "=" : "·"}</span>
              <span className={styles.bandChip} style={{ borderColor: analystBandColor ?? undefined }}>
                <span className={styles.bandChipLabel}>ANALYST</span>
                <span style={{ color: analystBandColor ?? undefined }}>
                  {BAND_LABEL[analyst.analyst_band as AssessmentBand] ?? analyst.analyst_band}
                </span>
              </span>
            </div>
          ) : null}
          {showTension ? (
            <p className={styles.axisNote}>
              <span className={styles.axisNoteTension}>ANALYST DISSENTS</span> — {analyst?.rationale}
            </p>
          ) : analyst?.dissents === false ? (
            <p className={styles.axisNote}>Analyst confirms ARGUS&apos;s reading. {analyst.rationale}</p>
          ) : analyst ? (
            <p className={styles.axisNote}>
              Recorded before ARGUS had assessed this subject, so there is nothing to compare it against yet. {analyst.rationale}
            </p>
          ) : null}
        </div>
      </div>

      <div className={styles.detailGrid}>
        <div className={`${styles.card} ${styles.detailCard}`}>
          <div className={styles.cardHead}>
            <span className={styles.cardTitle}>WHY IT SURFACED</span>
          </div>
          <div className={styles.signalsBody}>
            {signalsLoading ? (
              <Skeleton height={80} />
            ) : fired.length === 0 ? (
              <p className={styles.subLabel}>
                {signals.length === 0 ? "No assessment signal detail is available for this subject." : "No signal fired for this subject."}
              </p>
            ) : (
              fired.map((s) => {
                const pct = Math.round((s.magnitude ?? 0) * 100);
                const color = (s.magnitude ?? 0) > 0.7 ? "var(--risk-critical)" : (s.magnitude ?? 0) > 0.4 ? "var(--risk-high)" : "var(--risk-medium)";
                const title = signalTitle(s.signal_id) ?? s.summary;
                return (
                  <div key={s.signal_id} className={styles.signalRow}>
                    <div className={styles.signalTop}>
                      <span className={styles.signalTitle}>{title}</span>
                      <span className={styles.signalContribution}>+{s.contribution}</span>
                    </div>
                    <p className={styles.signalSummary}>{s.summary}</p>
                    <span className={styles.signalBarTrack}>
                      <span className={styles.signalBarFill} style={{ width: `${pct}%`, background: color }} />
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className={`${styles.card} ${styles.detailCard}`}>
          <div className={styles.cardHead}>
            <span className={styles.cardTitleTension}>WHAT ARGUS DOES NOT KNOW</span>
          </div>
          <div className={styles.unknownsBody}>
            <div className={styles.unknownRow}>
              <span className={styles.unknownDot} />
              <span>{100 - coverPct}% of the model could not be evaluated for this subject — evidence for those signals doesn&apos;t exist in this dataset.</span>
            </div>
            {notEvaluable.map((s) => (
              <div key={s.signal_id} className={styles.unknownRow}>
                <span className={styles.unknownDot} />
                <span>{s.summary}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.connections}>
        <span className={styles.connectionsLabel}>CONNECTIONS</span>
        {Object.entries(subject.connections ?? {}).map(([label, count]) => (
          <span key={label} className={styles.connectionChip}>
            {label} <span className={styles.connectionCount}>{count}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
