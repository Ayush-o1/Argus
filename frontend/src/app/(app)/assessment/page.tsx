"use client";

import { Gauge, HelpCircle, Play, ScanSearch } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import {
  useAssessmentModel,
  useAssessmentQueue,
  useAssessmentSummary,
  useLatestEvaluation,
  useRequestAssessmentRun,
} from "@/hooks/useAssessment";
import {
  BAND_LABEL,
  formatCoverage,
  formatScore,
  type AssessmentBand,
} from "@/lib/assessment";
import { cn } from "@/lib/cn";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./page.module.css";

/**
 * Where ARGUS's own risk assessment can be read, argued with, and checked.
 *
 * Three sections, in this order for a reason:
 *
 *   **The queue** — what to look at. Every row carries its evidence coverage
 *   beside its score, so no row can be read as more certain than it is.
 *
 *   **The model** — every question ARGUS asks, its weight, and why it is
 *   evidence of anything. Published so an analyst can disagree with the model
 *   rather than only with its output.
 *
 *   **The measurement** — precision and recall against the generator's planted
 *   storylines, including the planted phenomena no admissible signal can
 *   detect. Those are shown with their reasons rather than dropped, because a
 *   recall figure computed over only the detectable subset would be an average
 *   across a denominator chosen to flatter.
 */
export default function AssessmentPage() {
  const { data: session } = useSession();
  const canRun = session?.permissions?.includes("assessment:run") ?? false;

  const [band, setBand] = useState<AssessmentBand | null>("elevated");
  const summary = useAssessmentSummary();
  const model = useAssessmentModel();
  const queue = useAssessmentQueue({ band: band ?? undefined, page_size: 25 });
  const evaluation = useLatestEvaluation();
  const startRun = useRequestAssessmentRun();

  const counts = summary.data?.band_counts ?? [];
  const assessedTotal = summary.data?.assessed_total ?? 0;
  const lastRun = summary.data?.last_run ?? null;

  return (
    <PageShell
      title="Assessment"
      subtitle="What ARGUS concluded from evidence — and where it could not conclude anything"
      actions={
        canRun ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => startRun.mutate(true)}
            disabled={startRun.isPending}
          >
            <Play size={14} /> {startRun.isPending ? "Queueing…" : "Re-assess"}
          </Button>
        ) : null
      }
    >
      {summary.isLoading ? <Skeleton height={90} /> : null}

      {!summary.isLoading && assessedTotal === 0 ? (
        <EmptyState
          icon={Gauge}
          title="No assessment has been run"
          description={
            canRun
              ? "Nothing here is stale — it does not exist yet. Run an assessment to populate it."
              : "Nothing here is stale — it does not exist yet. An investigator or supervisor can run one."
          }
        />
      ) : null}

      {assessedTotal > 0 ? (
        <>
          {/* Counts across every band, summing to the population. The
              insufficient-evidence bucket is usually the largest, and it is
              shown at the same size as the rest: it is the figure that
              qualifies every other number on the page. */}
          <div className={styles.bands}>
            {counts.map((entry) => {
              const selected = band === entry.band;
              return (
                <button
                  key={entry.band}
                  type="button"
                  className={cn(styles.bandCard, selected && styles.bandCardSelected)}
                  onClick={() => setBand(selected ? null : (entry.band as AssessmentBand))}
                  title={entry.meaning}
                >
                  <span className={styles.bandCount}>{entry.count.toLocaleString()}</span>
                  <span className={styles.bandLabel}>
                    {BAND_LABEL[entry.band as AssessmentBand] ?? entry.band}
                  </span>
                  <span className={styles.bandShare}>
                    {entry.share === null ? "—" : `${Math.round(entry.share * 100)}% of ${assessedTotal.toLocaleString()}`}
                  </span>
                </button>
              );
            })}
          </div>

          {/* A failed run has no evidence summary, and rendering its empty
              counts as "saw 0 transfers" would describe a failure as an empty
              world. The two states are written as different sentences. */}
          {lastRun && lastRun.status !== "complete" ? (
            <p className={styles.runLine}>
              <strong className={styles.warn}>
                The most recent run {lastRun.status === "failed" ? "failed" : "is still running"}
              </strong>{" "}
              ({formatTimestamp(lastRun.started_at)}). The counts above are from the last run that
              finished, so they may be out of date.
              {lastRun.error ? <span className={styles.runError}> {lastRun.error}</span> : null}
            </p>
          ) : lastRun ? (
            <p className={styles.runLine}>
              Last run {formatTimestamp(lastRun.finished_at ?? lastRun.started_at)} ·{" "}
              {lastRun.model_version} · fingerprint {lastRun.model_fingerprint.slice(0, 12)} · saw{" "}
              {(lastRun.evidence_summary.transfers ?? 0).toLocaleString()} transfers,{" "}
              {(lastRun.evidence_summary.contacts ?? 0).toLocaleString()} communications
              {lastRun.search_truncated ? (
                <strong className={styles.warn}>
                  {" "}
                  · the cycle search hit its path limit, so this run under-reports
                </strong>
              ) : null}
            </p>
          ) : null}

          <Card
            title={band ? `${BAND_LABEL[band]} (${queue.data?.meta?.total ?? 0})` : "All subjects"}
          >
            {queue.isLoading ? (
              <Skeleton height={200} />
            ) : (queue.data?.data.length ?? 0) === 0 ? (
              <p className={styles.empty}>Nothing in this band.</p>
            ) : (
              <ul className={styles.queue}>
                {queue.data?.data.map((row) => (
                  <li key={row.subject_ref}>
                    <Link href={`/entities/${row.subject_ref}`} className={styles.row}>
                      <span className={styles.rowMain}>
                        <span className={styles.rowRef}>{row.subject_ref}</span>
                        <span className={styles.rowType}>{row.subject_type}</span>
                        <span className={styles.rowSummary}>
                          {row.signals
                            .filter((s) => s.evaluable && (s.magnitude ?? 0) > 0)
                            .map((s) => s.summary)
                            .join(" ") || row.band_meaning}
                        </span>
                      </span>
                      <span className={styles.rowScore}>
                        <span className={styles.rowScoreValue}>
                          {formatScore(row.score) ?? "—"}
                        </span>
                        {/* Never the score alone. */}
                        <span className={styles.rowCoverage}>
                          {formatCoverage(row.evidence_coverage)} of model
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      ) : null}

      <Card title="What ARGUS looks for">
        {model.isLoading ? (
          <Skeleton height={160} />
        ) : (
          <>
            <p className={styles.note}>
              Every question the model asks, with its weight and the reason it counts as evidence.
              A model whose questions are secret cannot be argued with.
            </p>
            <ul className={styles.signals}>
              {model.data?.signals.map((signal) => (
                <li key={signal.signal_id} className={styles.signal}>
                  <div className={styles.signalHead}>
                    <span className={styles.signalTitle}>{signal.title}</span>
                    <Badge tone="neutral">weight {signal.weight}</Badge>
                    <span className={styles.signalTypes}>{signal.subject_types.join(", ")}</span>
                  </div>
                  <p className={styles.signalQuestion}>{signal.question}</p>
                  <p className={styles.signalRationale}>{signal.rationale}</p>
                  <p className={styles.signalReads}>Reads: {signal.reads.join(", ")}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card title="How well it performs">
        {evaluation.isLoading ? (
          <Skeleton height={160} />
        ) : !evaluation.data ? (
          <p className={styles.note}>
            No evaluation has been published for this model. Precision and recall are measured
            against the scenario generator&apos;s planted storylines, which exist only in a
            synthetic dataset — on a real deployment there is nothing to measure against.
          </p>
        ) : (
          <EvaluationReport record={evaluation.data} />
        )}
      </Card>
    </PageShell>
  );
}

function EvaluationReport({
  record,
}: {
  record: NonNullable<ReturnType<typeof useLatestEvaluation>["data"]>;
}) {
  const r = record.report;
  const pct = (value: number | null) => (value === null ? "—" : `${Math.round(value * 100)}%`);

  return (
    <div className={styles.evaluation}>
      <p className={styles.note}>
        Measured {formatTimestamp(record.generated_at)} against model fingerprint{" "}
        {record.model_fingerprint.slice(0, 12)}. {r.labelled_subjects} subjects were planted:{" "}
        {r.labelled_by_storyline} in scripted storylines and {r.labelled_by_injected_anomaly_only}{" "}
        given anomalous behaviour without one.
      </p>

      <div className={styles.metrics}>
        <Metric
          label="Precision at elevated"
          value={pct(r.elevated.precision)}
          detail={`${r.elevated.true_positives} of ${r.elevated.selected} selected`}
        />
        <Metric
          label="Recall at elevated"
          value={pct(r.elevated.recall)}
          detail={`${r.elevated.true_positives} of ${r.elevated.labelled_total} planted`}
        />
        <Metric
          label="Precision, notable+"
          value={pct(r.notable_or_better.precision)}
          detail={`${r.notable_or_better.true_positives} of ${r.notable_or_better.selected}`}
        />
        {/* The stricter reading, beside the headline rather than instead of
            it. Where the two diverge, the difference is entities that really
            are anomalous and really were detected. */}
        <Metric
          label="Precision, scripted only"
          value={pct(r.elevated_storyline_only.precision)}
          detail="counting only scripted storylines"
        />
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Planted phenomenon</th>
            <th>Subjects</th>
            <th>Found</th>
            <th>Unassessable</th>
          </tr>
        </thead>
        <tbody>
          {r.per_storyline.map((row) => (
            <tr key={row.storyline_type} className={row.detectable ? undefined : styles.undetectable}>
              <td>
                {row.storyline_type.replace(/_/g, " ")}
                {!row.detectable ? (
                  <span className={styles.undetectableTag}>
                    <HelpCircle size={11} /> not detectable
                  </span>
                ) : null}
                {row.note ? <p className={styles.noteSmall}>{row.note}</p> : null}
              </td>
              <td>{row.planted_subjects}</td>
              <td>
                {row.reached_notable_or_better}
                {row.recall_at_notable !== null ? ` (${pct(row.recall_at_notable)})` : ""}
              </td>
              <td>{row.insufficient_evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.caveats}>
        <span className={styles.caveatTitle}>
          <ScanSearch size={13} /> What these numbers do not say
        </span>
        {r.caveats.map((caveat) => (
          <p key={caveat} className={styles.caveat}>
            {caveat}
          </p>
        ))}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className={styles.metric}>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricDetail}>{detail}</span>
    </div>
  );
}
