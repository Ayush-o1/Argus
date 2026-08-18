"use client";

import { AlertTriangle, HelpCircle, Network, Play, Share2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CardHeader } from "@/components/ui/CardHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import {
  useCorrelationClusters,
  useCorrelationEvaluation,
  useCorrelationLinks,
  useCorrelationModel,
  useCorrelationSummary,
  useRequestCorrelationRun,
} from "@/hooks/useCorrelation";
import { cn } from "@/lib/cn";
import {
  FAMILY_LABEL,
  TIER_LABEL,
  TIER_TONE,
  dimensionState,
  formatCoverage,
  formatStrength,
  type CorrelationLink,
  type CorrelationTier,
} from "@/lib/correlation";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./page.module.css";

/**
 * Where ARGUS's own correlations can be read, argued with, and checked.
 *
 * Four sections, in this order for a reason:
 *
 *   **The links** — what ARGUS connected. Every row shows the dimensions that
 *   produced it, including the ones that could not be evaluated, so no link can
 *   be read as more examined than it was.
 *
 *   **The clusters** — groups of linked findings, each with the load-bearing
 *   links holding it together. A group of eleven hanging off one uncertain link
 *   is not a discovery of eleven connected subjects, and it says so.
 *
 *   **The model** — every question ARGUS asks of a pair, which family it
 *   belongs to, and whether that family can establish a link at all. Published
 *   so an analyst can disagree with the model rather than only with its output.
 *
 *   **The measurement** — precision and recall against the generator's planted
 *   storylines. Three precision figures, because an unlabelled link is not a
 *   wrong link and a single number would have to pretend otherwise.
 */
export default function CorrelationPage() {
  const { data: session } = useSession();
  const canRun = session?.permissions?.includes("correlation:run") ?? false;

  const [tier, setTier] = useState<CorrelationTier | null>(null);
  const summary = useCorrelationSummary();
  const model = useCorrelationModel();
  const links = useCorrelationLinks({ tier: tier ?? undefined, page_size: 25 });
  const clusters = useCorrelationClusters(12);
  const evaluation = useCorrelationEvaluation();
  const startRun = useRequestCorrelationRun();

  const counts = summary.data?.tier_counts ?? [];
  const total = summary.data?.links_total ?? 0;
  const lastRun = summary.data?.last_run ?? null;

  return (
    <PageShell
      title="Correlation"
      subtitle="What ARGUS connected, on what grounds, and how far it could see"
      actions={
        canRun ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => startRun.mutate(true)}
            disabled={startRun.isPending}
          >
            <Play size={14} /> {startRun.isPending ? "Queueing…" : "Re-correlate"}
          </Button>
        ) : null
      }
    >
      {summary.isLoading ? <Skeleton height={90} /> : null}

      {!summary.isLoading && total === 0 ? (
        <EmptyState
          icon={Network}
          title="No correlation has been run"
          description={
            canRun
              ? "Nothing here is stale — it does not exist yet. Correlation runs over findings from the latest assessment, so assess first, then run this."
              : "Nothing here is stale — it does not exist yet. An investigator or supervisor can run one."
          }
        />
      ) : null}

      {total > 0 ? (
        <>
          <div className={styles.tiers}>
            {counts.map((entry) => (
              <button
                key={entry.tier}
                type="button"
                title={entry.meaning}
                className={cn(
                  styles.tierCard,
                  tier === entry.tier && styles.tierCardSelected,
                )}
                onClick={() => setTier(tier === entry.tier ? null : entry.tier)}
              >
                <span className={styles.tierCount}>{entry.count.toLocaleString()}</span>
                <span className={styles.tierLabel}>{TIER_LABEL[entry.tier]}</span>
                <span className={styles.tierShare}>
                  {entry.share === null ? "—" : `${Math.round(entry.share * 100)}% of links`}
                </span>
              </button>
            ))}
          </div>

          {lastRun ? <RunLine run={lastRun} /> : null}
        </>
      ) : null}

      {total > 0 ? (
        <Card>
          <CardHeader title={tier ? `${TIER_LABEL[tier]} links` : "All links"} subtitle={"Every dimension that was applied, including the ones that could not be"} />
          {links.isLoading ? (
            <Skeleton height={200} />
          ) : (links.data?.data.length ?? 0) === 0 ? (
            <p className={styles.note}>No links in this tier.</p>
          ) : (
            <ul className={styles.linkList}>
              {links.data?.data.map((link) => <LinkRow key={link.link_id} link={link} />)}
            </ul>
          )}
        </Card>
      ) : null}

      {(clusters.data?.length ?? 0) > 0 ? (
        <Card>
          <CardHeader title={"Groups"} subtitle={"Findings that connect to each other more than to anything else"} />
          <p className={styles.note}>
            Grouped by modularity rather than by connectivity. Following links from one subject to
            the next chains unrelated groups together — on this data that produced a single
            351-member &ldquo;group&rdquo; — so a group here means subjects more densely connected
            to each other than to the rest of the graph.
          </p>
          <ul className={styles.clusterList}>
            {clusters.data?.map((cluster) => (
              <li key={cluster.cluster_id} className={styles.cluster}>
                <div className={styles.clusterHead}>
                  <span className={styles.clusterSize}>{cluster.size}</span>
                  <span className={styles.clusterFamilies}>
                    {cluster.families.map((f) => FAMILY_LABEL[f] ?? f).join(" · ") ||
                      "no corroborating family"}
                  </span>
                  {cluster.over_merged ? (
                    <Badge tone="high" title="Larger than the size at which a group stops being a finding">
                      <AlertTriangle size={11} /> over-merged
                    </Badge>
                  ) : null}
                </div>
                <p className={styles.clusterBasis}>{cluster.basis}</p>
                <div className={styles.clusterMembers}>
                  {cluster.members.slice(0, 10).map((member) => (
                    <Link
                      key={member.subject_ref}
                      href={`/entities/${encodeURIComponent(member.subject_ref)}`}
                      className={styles.member}
                      title={`${member.subject_type} · ${member.degree} link${member.degree === 1 ? "" : "s"} inside this group`}
                    >
                      {member.subject_ref}
                    </Link>
                  ))}
                  {cluster.members.length > 10 ? (
                    <span className={styles.memberMore}>
                      +{cluster.members.length - 10} more
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card>
        <CardHeader title={"The model"} subtitle={"Every question ARGUS asks of a pair, and what it is allowed to read"} />
        {model.isLoading ? (
          <Skeleton height={200} />
        ) : (
          <>
            <div className={styles.families}>
              {model.data?.families.map((family) => (
                <div key={family.family} className={styles.family}>
                  <div className={styles.familyHead}>
                    <span className={styles.familyName}>
                      {FAMILY_LABEL[family.family] ?? family.family}
                    </span>
                    <Badge tone={family.identifying ? "medium" : "neutral"}>
                      {family.identifying ? "can establish a link" : "corroboration only"}
                    </Badge>
                  </div>
                  <p className={styles.familyMeaning}>{family.meaning}</p>
                  <p className={styles.familyCeiling}>
                    Contributes at most {family.ceiling.toFixed(2)} on its own
                  </p>
                </div>
              ))}
            </div>
            <p className={styles.noteSmall}>
              Spatial and temporal evidence adds to a link&rsquo;s strength but never counts
              towards corroboration. Being in one place, or busy in one week, is true of enormous
              numbers of unrelated pairs — so between them they are capped below the threshold at
              which anything is reported at all.
            </p>

            <ul className={styles.dimensions}>
              {model.data?.dimensions.map((dimension) => (
                <li key={dimension.dimension_id} className={styles.dimension}>
                  <div className={styles.dimensionHead}>
                    <span className={styles.dimensionTitle}>{dimension.label}</span>
                    <Badge tone="neutral">{FAMILY_LABEL[dimension.family] ?? dimension.family}</Badge>
                    <span className={styles.dimensionTypes}>
                      {dimension.subject_types.join(", ")}
                    </span>
                  </div>
                  <p className={styles.dimensionQuestion}>{dimension.question}</p>
                  <p className={styles.dimensionRationale}>{dimension.rationale}</p>
                  <p className={styles.dimensionReads}>reads: {dimension.reads.join(", ")}</p>
                </li>
              ))}
            </ul>

            <h3 className={styles.subheading}>Graphs the algorithms run on</h3>
            <p className={styles.noteSmall}>
              Every graph metric depends on which graph it ran over. Both are published with their
              relationship weights, because a ranking computed on accounts alone answers a
              different question from one computed over people, organisations and devices.
            </p>
            {model.data?.projections.map((projection) => (
              <div key={projection.projection} className={styles.projection}>
                <div className={styles.projectionHead}>
                  <span className={styles.dimensionTitle}>{projection.title}</span>
                  <span className={styles.dimensionTypes}>{projection.fingerprint}</span>
                </div>
                <p className={styles.dimensionRationale}>{projection.description}</p>
                <div className={styles.weights}>
                  {projection.relationships.map((rel) => (
                    <span key={rel.type} className={styles.weight} title={rel.rationale}>
                      {rel.type}
                      <strong>
                        {rel.weight_property ? `× ${rel.weight_property}` : `× ${rel.weight}`}
                      </strong>
                    </span>
                  ))}
                </div>
                {projection.caveats.map((caveat) => (
                  <p key={caveat} className={styles.caveat}>
                    {caveat}
                  </p>
                ))}
              </div>
            ))}
          </>
        )}
      </Card>

      <Card>
        <CardHeader title={"How well this works"} subtitle={"Measured against the generator's planted storylines, which the correlator cannot see"} />
        {evaluation.isLoading ? (
          <Skeleton height={160} />
        ) : !evaluation.data ? (
          <p className={styles.note}>
            No evaluation has been published for this model. Run a correlation with evaluation
            enabled to produce one.
          </p>
        ) : (
          <Evaluation report={evaluation.data.report} />
        )}
      </Card>
    </PageShell>
  );
}

function RunLine({ run }: { run: NonNullable<ReturnType<typeof useCorrelationSummary>["data"]>["last_run"] }) {
  if (!run) return null;
  if (run.status === "failed") {
    return (
      <p className={styles.runLine}>
        <span className={styles.warn}>
          Run {run.run_id} failed{run.error ? `: ${run.error}` : ""}.
        </span>{" "}
        The links below are from the last run that completed, and may be out of date.
      </p>
    );
  }
  return (
    <p className={styles.runLine}>
      Run {run.run_id} · {run.status} · {formatTimestamp(run.finished_at ?? run.started_at)} ·
      model {run.model_fingerprint.slice(0, 12)} · {run.anchors.toLocaleString()} findings
      correlated over {run.candidate_pairs.toLocaleString()} candidate pairs
      {run.assessment_run_id !== null ? ` · from assessment run ${run.assessment_run_id}` : ""}
      {run.keys_skipped > 0 ? (
        <>
          {" "}
          ·{" "}
          <span className={styles.warn}>
            {run.keys_skipped} shared keys too common to compare
          </span>
        </>
      ) : null}
      {run.search_truncated ? (
        <>
          {" "}
          ·{" "}
          <span className={styles.warn}>
            a funds-path search hit its limit, so an absent route is weaker evidence of absence
            than usual
          </span>
        </>
      ) : null}
    </p>
  );
}

function LinkRow({ link }: { link: CorrelationLink }) {
  const fired = link.dimensions.filter((d) => dimensionState(d) === "fired");
  const blind = link.dimensions.filter((d) => dimensionState(d) === "blind");

  return (
    <li className={styles.link}>
      <div className={styles.linkHead}>
        <Badge tone={TIER_TONE[link.tier]} title={link.tier_meaning}>
          {TIER_LABEL[link.tier]}
        </Badge>
        <Link href={`/entities/${encodeURIComponent(link.ref_a)}`} className={styles.ref}>
          {link.ref_a}
        </Link>
        <Share2 size={12} className={styles.linkIcon} />
        <Link href={`/entities/${encodeURIComponent(link.ref_b)}`} className={styles.ref}>
          {link.ref_b}
        </Link>
        <span className={styles.linkStrength}>
          {formatStrength(link.strength)}
          <span className={styles.linkCoverage}>
            {" "}
            on {formatCoverage(link.coverage)} of {link.applicable_dimensions} dimensions
          </span>
        </span>
      </div>

      {fired.map((dimension) => (
        <p key={dimension.dimension_id} className={styles.reason}>
          <span className={styles.reasonName}>
            {FAMILY_LABEL[dimension.family] ?? dimension.family}
          </span>
          {dimension.summary}
        </p>
      ))}

      {/* Stated, not omitted. A pair whose spatial dimension could not be
          evaluated has not been shown to be far apart. */}
      {blind.length > 0 ? (
        <p className={styles.blind}>
          {blind.length} dimension{blind.length === 1 ? "" : "s"} could not be evaluated:{" "}
          {blind.map((d) => d.dimension_id).join(", ")}
        </p>
      ) : null}
    </li>
  );
}

function Evaluation({
  report,
}: {
  report: NonNullable<ReturnType<typeof useCorrelationEvaluation>["data"]>["report"];
}) {
  return (
    <div className={styles.evaluation}>
      <div className={styles.metrics}>
        <Metric
          value={report.discriminative.precision}
          label="Discriminative precision"
          detail={`Over the ${report.discriminative.selected} links where both subjects are planted in some storyline — the only pairs ground truth can judge`}
        />
        <Metric
          value={report.discriminative.recall}
          label="Recall"
          detail={`${report.discriminative.true_positives} of ${report.discriminative.labelled_total} planted pairs recovered`}
        />
        <Metric
          value={report.strict.precision}
          label="Strict precision"
          detail={`Counts all ${report.unlabelled_links} unlabelled links as wrong. A lower bound, and by construction an underestimate`}
        />
        <Metric
          value={report.cluster_purity}
          label="Group purity"
          detail={`Across ${report.clusters} groups covering ${report.clustered_subjects} subjects`}
        />
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Planted phenomenon</th>
            <th>Pairs</th>
            <th>Recovered</th>
            <th>Recall</th>
          </tr>
        </thead>
        <tbody>
          {report.per_storyline.map((row) => (
            <tr
              key={row.storyline_type}
              className={cn(!row.reachable && styles.unreachable)}
            >
              <td>
                {row.storyline_type}
                {!row.reachable ? (
                  <span className={styles.unreachableTag} title={row.note}>
                    <HelpCircle size={11} /> cannot be correlated
                  </span>
                ) : null}
                {row.reachable && row.note ? (
                  <span className={styles.unreachableTag} title={row.note}>
                    <HelpCircle size={11} /> partly reachable
                  </span>
                ) : null}
              </td>
              <td>{row.planted_pairs}</td>
              <td>{row.recovered_pairs}</td>
              <td>{row.pair_recall === null ? "—" : row.pair_recall.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Dimension</th>
            <th>Fired</th>
            <th>Could not evaluate</th>
            <th>Precision within links</th>
          </tr>
        </thead>
        <tbody>
          {report.per_dimension.map((row) => (
            <tr key={row.dimension_id}>
              <td>{row.dimension_id}</td>
              <td>{row.fired}</td>
              <td>{row.not_evaluable}</td>
              <td>
                {row.precision_within_links === null
                  ? "—"
                  : row.precision_within_links.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.caveats}>
        <div className={styles.caveatTitle}>
          <HelpCircle size={12} /> What these numbers do not say
        </div>
        {report.caveats.map((caveat) => (
          <p key={caveat} className={styles.caveat}>
            {caveat}
          </p>
        ))}
      </div>
    </div>
  );
}

function Metric({
  value,
  label,
  detail,
}: {
  value: number | null;
  label: string;
  detail: string;
}) {
  return (
    <div className={styles.metric}>
      {/* An em dash rather than 0. Nothing was selected, which is a different
          statement from everything selected being wrong. */}
      <span className={styles.metricValue}>{value === null ? "—" : value.toFixed(2)}</span>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricDetail}>{detail}</span>
    </div>
  );
}
