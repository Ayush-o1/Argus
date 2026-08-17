"use client";

import { AlertTriangle, Check, HelpCircle, Minus } from "lucide-react";
import { useSubjectAssessment } from "@/hooks/useAssessment";
import {
  BAND_LABEL,
  BAND_TONE,
  formatCoverage,
  formatScore,
  type AssessmentBand,
  type SignalOutcome,
} from "@/lib/assessment";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import styles from "./AssessmentPanel.module.css";

/**
 * ARGUS's own assessment of one entity, with its whole working shown.
 *
 * The panel is built around one rule: a reader must always be able to tell
 * these three states apart —
 *
 *   a signal fired,
 *   a signal was evaluated and came back clean,
 *   a signal could not be evaluated at all.
 *
 * The third is the one every previous version of this surface erased. It is
 * given its own section, its own icon, and its own count, because "we have no
 * transaction history for this person" is the most important thing on the page
 * when it is true, and it renders as reassuring silence everywhere it is not
 * said out loud.
 */
export function AssessmentPanel({ subjectRef }: { subjectRef: string }) {
  const { data, isLoading, isError } = useSubjectAssessment(subjectRef);

  if (isLoading) return <Skeleton height={140} />;

  if (isError || !data) {
    return (
      <p className={styles.absent}>
        ARGUS has published no assessment for this entity. Either its type is not assessed
        (assessment covers people, organisations, accounts and shipments) or no assessment run has
        covered it yet. This is not a statement that it is low risk.
      </p>
    );
  }

  const band = data.band as AssessmentBand;
  const score = formatScore(data.score);
  const coverage = formatCoverage(data.evidence_coverage);

  const fired = data.signals.filter((s) => s.evaluable && (s.magnitude ?? 0) > 0);
  const clean = data.signals.filter((s) => s.evaluable && (s.magnitude ?? 0) === 0);
  const blind = data.signals.filter((s) => !s.evaluable);

  return (
    <div className={styles.wrap}>
      <div className={styles.headline}>
        <Badge tone={BAND_TONE[band] ?? "neutral"}>{BAND_LABEL[band] ?? band}</Badge>
        {score !== null ? (
          <span className={styles.score}>
            <span className={styles.scoreValue}>{score}</span>
            <span className={styles.scoreMax}>/ 100</span>
          </span>
        ) : (
          <span className={styles.noScore}>No score</span>
        )}
      </div>

      {/* The denominator, never optional and never smaller than the number it
          qualifies by more than a step. */}
      <p className={styles.coverage}>
        {score === null
          ? `Only ${coverage} of the model could be evaluated — too little to score.`
          : `Over the ${coverage} of the model ARGUS could evaluate for this entity (${data.evaluable_weight} of ${data.total_weight} weight).`}
      </p>

      <p className={styles.meaning}>{data.band_meaning}</p>

      {fired.length > 0 ? (
        <Section title={`What fired (${fired.length})`}>
          {fired.map((signal) => (
            <SignalRow key={signal.signal_id} signal={signal} state="fired" />
          ))}
        </Section>
      ) : null}

      {blind.length > 0 ? (
        <Section title={`Could not be evaluated (${blind.length})`}>
          {blind.map((signal) => (
            <SignalRow key={signal.signal_id} signal={signal} state="blind" />
          ))}
        </Section>
      ) : null}

      {clean.length > 0 ? (
        <Section title={`Examined, nothing found (${clean.length})`}>
          {clean.map((signal) => (
            <SignalRow key={signal.signal_id} signal={signal} state="clean" />
          ))}
        </Section>
      ) : null}

      <p className={styles.footer}>
        {data.model_version} · fingerprint {data.model_fingerprint.slice(0, 12)} ·{" "}
        {new Date(data.computed_at).toLocaleString()}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.section}>
      <span className={styles.sectionTitle}>{title}</span>
      {children}
    </div>
  );
}

const STATE_ICON = {
  fired: AlertTriangle,
  clean: Check,
  blind: HelpCircle,
} as const;

function SignalRow({
  signal,
  state,
}: {
  signal: SignalOutcome;
  state: "fired" | "clean" | "blind";
}) {
  const Icon = STATE_ICON[state];
  return (
    <div className={styles.signal}>
      <span className={styles[state]}>
        <Icon size={13} />
      </span>
      <span className={styles.signalBody}>
        <span className={styles.signalSummary}>{signal.summary}</span>
        {state === "fired" ? (
          <span className={styles.signalMeta}>
            weight {signal.weight} · strength {Math.round((signal.magnitude ?? 0) * 100)}%
          </span>
        ) : null}
        {state === "blind" ? (
          <span className={styles.signalMeta}>
            <Minus size={10} /> no evidence either way
          </span>
        ) : null}
      </span>
    </div>
  );
}
