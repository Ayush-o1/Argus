"use client";

import { useRouter } from "next/navigation";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { BAND_LABEL } from "@/lib/assessment";
import type { GraphNode } from "@/lib/types";
import { nextFixtureAnalystJudgements, nextFixtureSignals } from "@/lib/next/fixtures";
import { DIVERGENCE_THRESHOLD, bandColorVar } from "@/lib/next/format";
import { NEXT_MODE_PATH } from "@/lib/next/modeRouting";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./LeadDossier.module.css";

/**
 * The assessment dossier for whatever subject is selected — the design's
 * centrepiece: ARGUS's score and an analyst's, kept as two independent
 * readings on one axis, never merged into a single number. This rule is
 * absolute across the whole product (see `assessmentTier()` in
 * `lib/theme.ts`), not a style choice specific to this screen.
 */
export function LeadDossier({ subject }: { subject: GraphNode }) {
  const router = useRouter();
  const pins = useNextScopeStore((s) => s.pins);
  const togglePin = useNextScopeStore((s) => s.togglePin);
  const setLens = useNextScopeStore((s) => s.setLens);
  const setFocus = useNextScopeStore((s) => s.setFocus);

  const assessment = subject.assessment;
  const analyst = nextFixtureAnalystJudgements[subject.id];
  const signals = nextFixtureSignals[subject.id] ?? [];
  const fired = signals.filter((s) => s.evaluable && (s.magnitude ?? 0) > 0);
  const notEvaluable = signals.filter((s) => !s.evaluable);

  const argusScore = assessment?.score ?? null;
  const argusX = argusScore ?? 0;
  const analystX = analyst?.score ?? 0;
  const divergence = analyst && argusScore !== null ? Math.abs(argusScore - analyst.score) : 0;
  const showTension = !!analyst && divergence >= DIVERGENCE_THRESHOLD;
  const coverage = assessment?.coverage ?? 0;
  const coverPct = Math.round(coverage * 100);
  const bandColor = bandColorVar(assessment?.band);

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
            {showTension ? "MACHINE AND ANALYST DISAGREE" : analyst ? "CORROBORATED BY ANALYST" : "UNREVIEWED BY ANALYST"}
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
                  <span className={styles.scoreValue}>{analyst.score}</span>
                  <span className={styles.scoreDenominator}>/100</span>
                </div>
                <div className={styles.bandLabel}>{BAND_LABEL[analyst.band]}</div>
                <div className={styles.subLabel}>
                  {analyst.by} · {analyst.at}
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
            {showTension ? (
              <span
                className={styles.tensionBand}
                style={{ left: `${Math.min(argusX, analystX)}%`, width: `${Math.abs(argusX - analystX)}%` }}
              />
            ) : null}
            <span className={styles.marker} style={{ left: `${argusX}%`, background: bandColor }} />
            <span className={styles.markerLabel} style={{ left: `${argusX}%`, color: bandColor }}>
              ARGUS
            </span>
            {analyst ? (
              <>
                <span className={styles.marker} style={{ left: `${analystX}%`, background: "var(--text-primary)" }} />
                <span className={styles.markerLabelBottom} style={{ left: `${analystX}%` }}>
                  ANALYST
                </span>
              </>
            ) : null}
          </div>
          {showTension ? (
            <p className={styles.axisNote}>
              <span className={styles.axisNoteTension}>DIVERGENCE {divergence} PTS</span> — {analyst?.note}
            </p>
          ) : analyst ? (
            <p className={styles.axisNote}>
              Machine and analyst agree within {divergence} points. {analyst.note}
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
            {fired.length === 0 ? (
              <p className={styles.subLabel}>No signal was evaluable for this subject.</p>
            ) : (
              fired.map((s) => {
                const pct = Math.round((s.magnitude ?? 0) * 100);
                const color = (s.magnitude ?? 0) > 0.7 ? "var(--risk-critical)" : (s.magnitude ?? 0) > 0.4 ? "var(--risk-high)" : "var(--risk-medium)";
                const title = (s.detail as { title?: string })?.title ?? s.summary;
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
