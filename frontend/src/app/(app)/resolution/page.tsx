"use client";

import {
  GitMerge,
  Play,
  RotateCcw,
  ScanSearch,
  Split,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { ComparisonTable } from "@/components/resolution/ComparisonTable";
import { EvidenceMeter } from "@/components/resolution/EvidenceMeter";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import {
  useClusters,
  useDecideCandidate,
  useEvaluations,
  useResolutionDecisions,
  useResolutionQueue,
  useResolutionRuns,
  useReverseDecision,
  useStartResolutionRun,
} from "@/hooks/useResolution";
import { cn } from "@/lib/cn";
import { formatTimestamp } from "@/lib/provenance";
import { BAND_MEANING, type Band, type Candidate, formatScore } from "@/lib/resolution";
import styles from "./page.module.css";

const BANDS: Band[] = ["review", "auto", "insufficient", "reject"];

const BAND_LABEL: Record<Band, string> = {
  review: "Needs a decision",
  auto: "Merged automatically",
  insufficient: "Too little to say",
  reject: "Ruled out",
};

/**
 * Entity resolution — deciding when two records are the same real thing.
 *
 * Three things drive the layout, in order of how badly getting them wrong
 * would mislead someone:
 *
 *  1. **A contested cluster leads the page.** It means ARGUS has been told two
 *     contradictory things about an identity and has refused to pick one. That
 *     is a finding, not a footnote, and burying it would leave people acting on
 *     a merged identity nobody agreed to.
 *  2. **The queue length is never shown alone.** "12 pending" reads as "12
 *     duplicates exist" unless it sits next to how many pairs the matcher
 *     scored, declined to raise, and ruled out.
 *  3. **Every score carries the evidence it came from.** See `EvidenceMeter`.
 */
export default function ResolutionPage() {
  const [band, setBand] = useState<Band>("review");
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [rationale, setRationale] = useState("");
  const [reversing, setReversing] = useState<number | null>(null);
  const [reverseReason, setReverseReason] = useState("");

  const { data: queue, isLoading } = useResolutionQueue(band);
  const { data: clusterData } = useClusters();
  const { data: decisions } = useResolutionDecisions();
  const { data: runs } = useResolutionRuns();
  const { data: evaluations } = useEvaluations();
  const { data: session } = useSession();

  const canDecide = session?.permissions.includes("resolution:decide") ?? false;
  const canManage = session?.permissions.includes("resolution:manage") ?? false;

  const decide = useDecideCandidate();
  const reverse = useReverseDecision();
  const startRun = useStartResolutionRun();

  const counts = queue?.counts ?? {};
  const candidates = queue?.candidates ?? [];
  const contested = (clusterData?.clusters ?? []).filter((c) => c.contested);
  const latestRun = runs?.[0];

  // Live pairs only. A withdrawn candidate is one the *current* model no longer
  // produces, so counting it in the denominator made every band's share of "all
  // pairs" wrong — the reject band read 93% when it was 99.8% of what the
  // current model actually scored.
  const live = (byStatus: Record<string, number> | undefined) =>
    (byStatus?.open ?? 0) + (byStatus?.decided ?? 0);
  const total = Object.values(counts).reduce((sum, byStatus) => sum + live(byStatus), 0);
  const withdrawn = Object.values(counts).reduce(
    (sum, byStatus) => sum + (byStatus.withdrawn ?? 0),
    0,
  );

  const submitDecision = (verdict: "same" | "different") => {
    if (!selected || rationale.trim().length < 3) return;
    decide.mutate(
      { candidateId: selected.candidate_id, verdict, rationale: rationale.trim() },
      {
        onSuccess: () => {
          setSelected(null);
          setRationale("");
        },
      },
    );
  };

  return (
    <PageShell
      title="Entity Resolution"
      subtitle="When two records describe the same real thing — and when ARGUS will not say"
      actions={
        canManage ? (
          <div className={styles.headerActions}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => startRun.mutate({ applyAuto: false })}
              disabled={startRun.isPending}
              title="Score the population without merging anything"
            >
              <ScanSearch size={15} /> Score only
            </Button>
            <Button
              size="sm"
              onClick={() => startRun.mutate({ applyAuto: true })}
              disabled={startRun.isPending}
            >
              <Play size={15} /> Run matcher
            </Button>
          </div>
        ) : null
      }
    >
      {/* 1. Contradictions ARGUS has refused to resolve. */}
      {contested.length > 0 ? (
        <div className={styles.contestedBanner}>
          <TriangleAlert size={18} />
          <div>
            <strong>
              {contested.length} contested {contested.length === 1 ? "identity" : "identities"}
            </strong>
            <p className={styles.bannerBody}>
              A chain of merges has joined these records into one identity, while other decisions
              say some of them are different. ARGUS has not chosen which decision to discard, so
              until someone does, treat everything on these records as unsettled.
            </p>
            <ul className={styles.contestedList}>
              {contested.map((cluster) => (
                <li key={cluster.cluster_key}>
                  <strong>{cluster.members.join(" · ")}</strong>
                  <span className={styles.contestedReason}>{cluster.contested_reason}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {/* 2. The queue, always against its denominators. */}
      <div className={styles.summary}>
        {BANDS.map((key) => {
          const open = counts[key]?.open ?? 0;
          const decided = counts[key]?.decided ?? 0;
          // The headline is how many pairs landed in this band, not how many
          // are still open. An automatic merge is decided the moment it is
          // made, so an open-only count would show "0 merged automatically" on
          // a day the matcher merged a dozen.
          // Only the review band is actually waiting on anyone. Calling 1,552
          // ruled-out pairs "awaiting a decision" would invent a backlog that
          // does not exist.
          const openLabel = key === "review" ? "awaiting a decision" : "recorded";
          const parts = [
            open > 0 ? `${open.toLocaleString()} ${openLabel}` : null,
            decided > 0 ? `${decided.toLocaleString()} decided` : null,
          ].filter(Boolean);
          return (
            <button
              key={key}
              type="button"
              className={cn(styles.bandCard, band === key && styles.bandCardActive)}
              onClick={() => {
                setBand(key);
                setSelected(null);
              }}
            >
              <span className={styles.bandCount}>{(open + decided).toLocaleString()}</span>
              <span className={styles.bandLabel}>{BAND_LABEL[key]}</span>
              <span className={styles.bandMeta}>
                {parts.length ? parts.join(" · ") : "none"}
                {total > 0 ? ` · of ${total.toLocaleString()} scored` : ""}
              </span>
            </button>
          );
        })}
      </div>
      <p className={styles.bandMeaning}>
        {BAND_MEANING[band]}
        {withdrawn > 0 ? (
          <>
            {" "}
            A further {withdrawn.toLocaleString()} pair
            {withdrawn === 1 ? " is" : "s are"} no longer produced by the current model and{" "}
            {withdrawn === 1 ? "has" : "have"} been withdrawn from the queue.
          </>
        ) : null}
      </p>

      <div className={styles.columns}>
        <div className={styles.queueColumn}>
          {isLoading ? (
            <Skeleton height={200} />
          ) : candidates.length === 0 ? (
            <EmptyState
              icon={Users}
              title={`Nothing in "${BAND_LABEL[band].toLowerCase()}"`}
              description={
                band === "review"
                  ? "No pair is currently waiting on a person. That is not the same as " +
                    "'there are no duplicates' — it means nothing scored between the review " +
                    "and automatic thresholds under the current model. Run the matcher to " +
                    "re-score the population."
                  : "Nothing has landed in this band under the current model."
              }
            />
          ) : (
            <ul className={styles.candidateList}>
              {candidates.map((candidate) => (
                <li key={candidate.candidate_id}>
                  <button
                    type="button"
                    className={cn(
                      styles.candidate,
                      selected?.candidate_id === candidate.candidate_id && styles.candidateActive,
                    )}
                    onClick={() => {
                      setSelected(candidate);
                      setRationale("");
                    }}
                  >
                    <div className={styles.candidateRefs}>
                      <code>{candidate.left_ref}</code>
                      <GitMerge size={13} />
                      <code>{candidate.right_ref}</code>
                    </div>
                    <div className={styles.candidateScore}>
                      {formatScore(candidate.score)}
                      <span className={styles.candidateEvidence}>
                        {Math.round(candidate.evidence_weight * 100)}% evidence
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={styles.detailColumn}>
          {selected ? (
            <Card className={styles.detail}>
              <div className={styles.detailHeader}>
                <div>
                  <div className={styles.detailTitle}>
                    <code>{selected.left_ref}</code> and <code>{selected.right_ref}</code>
                  </div>
                  <div className={styles.detailMeta}>
                    {selected.entity_type} · scored by {selected.model_version}{" "}
                    <span className={styles.fingerprint}>{selected.model_fingerprint}</span>
                  </div>
                </div>
                <Badge tone={selected.band === "auto" ? "ok" : "medium"}>
                  {BAND_LABEL[selected.band]}
                </Badge>
              </div>

              <EvidenceMeter
                score={selected.score}
                evidenceWeight={selected.evidence_weight}
                className={styles.detailMeter}
              />

              {/* The matcher's own reason, verbatim. A band with no stated
                  reason is an unexplained decision. */}
              <p className={styles.bandReason}>{selected.band_reason}</p>

              {/* Why these two were ever compared. Without it an analyst cannot
                  tell a coincidental name collision from a shared identifier. */}
              <div className={styles.blocking}>
                <span className={styles.blockingLabel}>Compared because they share</span>
                {selected.blocking_keys.length ? (
                  selected.blocking_keys.map((key) => (
                    <code key={key} className={styles.blockingKey}>
                      {key.split(":").slice(1).join(":")}
                    </code>
                  ))
                ) : (
                  <span className={styles.muted}>no recorded blocking key</span>
                )}
              </div>

              <ComparisonTable
                comparisons={selected.comparisons}
                leftRef={selected.left_ref}
                rightRef={selected.right_ref}
              />

              {selected.status === "decided" ? (
                <p className={styles.muted}>
                  This pair has already been decided. Reverse the decision below rather than
                  deciding again, so the change is recorded as a reversal.
                </p>
              ) : canDecide ? (
                <div className={styles.decideBox}>
                  <label htmlFor="rationale" className={styles.decideLabel}>
                    Why? Required — the next analyst reads this, not the score.
                  </label>
                  <textarea
                    id="rationale"
                    className={styles.rationale}
                    rows={3}
                    value={rationale}
                    onChange={(event) => setRationale(event.target.value)}
                    placeholder="e.g. Same phone and date of birth; the second record is a partner feed's spelling of the same name."
                  />
                  <div className={styles.decideActions}>
                    <Button
                      size="sm"
                      onClick={() => submitDecision("same")}
                      disabled={rationale.trim().length < 3 || decide.isPending}
                    >
                      <GitMerge size={15} /> Same entity
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => submitDecision("different")}
                      disabled={rationale.trim().length < 3 || decide.isPending}
                    >
                      <Split size={15} /> Different entities
                    </Button>
                  </div>
                  <p className={styles.reversibleNote}>
                    Both records are kept either way. A merge is a recorded claim about the two,
                    never an edit to either, so it can be reversed without anything being restored.
                  </p>
                </div>
              ) : (
                <p className={styles.muted}>
                  Your role can read the queue but not decide. Deciding that two records are the
                  same changes what every other surface shows about both.
                </p>
              )}
            </Card>
          ) : (
            <Card className={styles.detail}>
              <EmptyState
                icon={ScanSearch}
                title="Select a pair"
                description="Every attribute the matcher compared is shown side by side, including the ones it could not compare at all."
              />
            </Card>
          )}
        </div>
      </div>

      {/* 3. The ledger. Reversibility is only real if it is reachable. */}
      <Card className={styles.section}>
        <h2 className={styles.sectionTitle}>Decisions</h2>
        <p className={styles.sectionBody}>
          Append-only. Reversing a merge records the opposite decision rather than deleting the
          original, because &ldquo;merged then un-merged&rdquo; is a different history from
          &ldquo;never merged&rdquo;.
        </p>
        {(decisions ?? []).length === 0 ? (
          <p className={styles.muted}>No decisions recorded yet.</p>
        ) : (
          <ul className={styles.decisionList}>
            {(decisions ?? []).map((decision) => (
              <li key={decision.decision_id} className={styles.decision}>
                <div className={styles.decisionMain}>
                  <Badge tone={decision.verdict === "same" ? "ok" : "neutral"}>
                    {decision.verdict === "same" ? "Same" : "Different"}
                  </Badge>
                  <code>{decision.left_ref}</code>
                  <code>{decision.right_ref}</code>
                  <span className={styles.decisionBy}>
                    {decision.decided_by_display}
                    {decision.decided_by_kind === "matcher" ? " (matcher)" : ""}
                  </span>
                  <span className={styles.decisionAt}>{formatTimestamp(decision.decided_at)}</span>
                  {canManage && decision.reverses_decision_id === null ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setReversing(decision.decision_id);
                        setReverseReason("");
                      }}
                    >
                      <RotateCcw size={14} /> Reverse
                    </Button>
                  ) : null}
                </div>
                <p className={styles.decisionReason}>{decision.rationale}</p>
                {reversing === decision.decision_id ? (
                  <div className={styles.reverseBox}>
                    <textarea
                      className={styles.rationale}
                      rows={2}
                      value={reverseReason}
                      onChange={(event) => setReverseReason(event.target.value)}
                      placeholder="Why is this decision being reversed?"
                    />
                    <div className={styles.decideActions}>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={reverseReason.trim().length < 3 || reverse.isPending}
                        onClick={() =>
                          reverse.mutate(
                            {
                              decisionId: decision.decision_id,
                              rationale: reverseReason.trim(),
                            },
                            { onSuccess: () => setReversing(null) },
                          )
                        }
                      >
                        Record reversal
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setReversing(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 4. How well the matcher does, and where it was measured. */}
      <Card className={styles.section}>
        <h2 className={styles.sectionTitle}>How well does this work?</h2>
        {(evaluations ?? []).length === 0 ? (
          <p className={styles.muted}>
            No evaluation has been published for this model yet. Until one is, the scores above are
            unmeasured — treat them as a ranking, not a probability.
          </p>
        ) : (
          <div className={styles.evaluations}>
            {(evaluations ?? []).slice(0, 2).map((row) => (
              <div key={row.evaluation_id} className={styles.evaluation}>
                <div className={styles.evaluationHead}>
                  <Badge tone={row.dataset === "analyst" ? "accent" : "neutral"}>
                    {row.dataset === "analyst" ? "Measured on real decisions" : "Constructed set"}
                  </Badge>
                  <span className={styles.fingerprint}>{row.model_fingerprint}</span>
                  <span className={styles.decisionAt}>{formatTimestamp(row.ran_at)}</span>
                </div>
                <dl className={styles.metrics}>
                  <Metric label="Precision" value={row.metrics.overall.precision} />
                  <Metric label="Recall (scorer)" value={row.metrics.overall.recall} />
                  <Metric
                    label="Recall (whole pipeline)"
                    value={row.metrics.overall.pipeline_recall}
                  />
                  <Metric label="Pairs" value={row.metrics.overall.pairs} raw />
                </dl>
                {/* The note says what the dataset is and what it cannot tell
                    you. A precision figure with no stated population is a
                    number pretending to be a guarantee. */}
                {row.notes ? <p className={styles.evaluationNote}>{row.notes}</p> : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      {latestRun ? (
        <p className={styles.runFooter}>
          Last run {formatTimestamp(latestRun.started_at)} · {latestRun.status} ·{" "}
          {latestRun.profiles_examined.toLocaleString()} records examined,{" "}
          {latestRun.pairs_scored.toLocaleString()} pairs scored · model{" "}
          <span className={styles.fingerprint}>{latestRun.model_fingerprint}</span>
        </p>
      ) : null}
    </PageShell>
  );
}

function Metric({
  label,
  value,
  raw = false,
}: {
  label: string;
  value: number | null | undefined;
  raw?: boolean;
}) {
  return (
    <div className={styles.metric}>
      <dt>{label}</dt>
      {/* Null means the measurement has no denominator, which is a different
          statement from zero and is shown as such. */}
      <dd>
        {value === null || value === undefined
          ? "not measurable"
          : raw
            ? value.toLocaleString()
            : `${(value * 100).toFixed(1)}%`}
      </dd>
    </div>
  );
}
