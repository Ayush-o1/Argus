"use client";

import { BarChart3 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/Button";
import { useHasPermission } from "@/hooks/useAuth";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { Table, type TableColumn } from "@/components/ui/Table";
import { cn } from "@/lib/cn";
import {
  type Community,
  type Cycle,
  type RankedEntity,
  type RiskPropagationResult,
  type ProjectedResult,
  type ProjectionProvenance,
  type SimilarEntity,
  type TransactionAnomaly,
  useAnalyticsJob,
} from "@/hooks/useAnalytics";
import styles from "./page.module.css";

type AlgorithmId =
  | "pagerank"
  | "betweenness"
  | "louvain"
  | "similar"
  | "risk-propagation"
  | "cycle-detection"
  | "anomalies";

interface AlgorithmDef {
  id: AlgorithmId;
  /** The investigative question this run answers — what the analyst is
   * actually here for. Leading with "PageRank" told a first-time user what
   * the code does, not what they would learn by running it. */
  question: string;
  /** The underlying method, kept visible as supporting credibility. */
  name: string;
  description: string;
  needsInput?: "entity" | "seeds";
}

const ALGORITHMS: AlgorithmDef[] = [
  {
    id: "pagerank",
    question: "Who holds the most influence?",
    name: "PageRank",
    description: "Globally influential entities — importance amplified by connections to other important entities.",
  },
  {
    id: "betweenness",
    question: "Who connects otherwise separate groups?",
    name: "Betweenness Centrality",
    description: "Bridge entities connecting otherwise disconnected groups. High score = key connector.",
  },
  {
    id: "louvain",
    question: "Which clusters operate together?",
    name: "Louvain Communities",
    description: "Partitions the transaction network into densely connected clusters, ranked by average risk.",
  },
  {
    id: "similar",
    question: "Who else behaves like this entity?",
    name: "Node2Vec similarity",
    description: "Graph embeddings + cosine similarity — entities occupying a structurally similar role.",
    needsInput: "entity",
  },
  {
    id: "risk-propagation",
    question: "How far does this entity's risk spread?",
    name: "Risk Propagation",
    description: "Spreads risk from a seed entity across the network, attenuating by hop distance.",
    needsInput: "seeds",
  },
  {
    id: "cycle-detection",
    question: "Is money moving in circles?",
    name: "Cycle Detection",
    description: "Circular money-movement paths (A → B → ... → A) — the classic laundering-ring signature.",
  },
  {
    id: "anomalies",
    question: "Which transactions don't fit the pattern?",
    name: "Isolation Forest + z-score",
    description: "Unsupervised outlier detection over per-account behavior — independent of any ground-truth flags.",
  },
];

type AnyResult =
  | ProjectedResult<unknown>
  | RankedEntity[]
  | { communities: Community[]; total_communities: number }
  | SimilarEntity[]
  | RiskPropagationResult
  | Cycle[]
  | TransactionAnomaly[];

export default function AnalyticsPage() {
  const [active, setActive] = useState<AlgorithmId>("pagerank");
  // Reading results and starting jobs are separate permissions: a viewer or
  // auditor may look at what previous runs produced but not spend the cluster's
  // CPU. Disabling the control explains that in place, rather than letting the
  // click fail with a 403 the analyst has to interpret.
  const canRun = useHasPermission("analytics:run");

  const [entityInput, setEntityInput] = useState("");
  const job = useAnalyticsJob<AnyResult>();

  const algorithm = ALGORITHMS.find((a) => a.id === active)!;

  const run = () => {
    job.reset();
    if (active === "similar") {
      if (!entityInput.trim()) return;
      job.start.mutate({ path: `/api/analytics/similar/${entityInput.trim()}?top_k=10` });
    } else if (active === "risk-propagation") {
      if (!entityInput.trim()) return;
      job.start.mutate({
        path: "/api/analytics/risk-propagation",
        body: { seed_ids: [entityInput.trim()], max_hops: 3 },
      });
    } else {
      job.start.mutate({ path: `/api/analytics/${active}` });
    }
  };

  const handleSelect = (id: AlgorithmId) => {
    setActive(id);
    setEntityInput("");
    job.reset();
  };

  const status = job.job.data?.status;
  const raw = job.job.data?.result;

  // The projection-based algorithms return `{ projection, results }`; the
  // others return their rows directly. Unwrapped here so every renderer below
  // receives rows, and the graph is rendered once, above them all.
  const projection = isProjected(raw) ? raw.projection : null;
  const result = isProjected(raw) ? (raw.results as AnyResult) : raw;

  return (
    <PageShell
      title="Analytics Engine"
      subtitle="Graph algorithms and community detection, run on demand over the live transaction network"
    >
      <div className={styles.layout}>
        <div className={styles.algoList}>
          {ALGORITHMS.map((a) => (
            <button
              key={a.id}
              type="button"
              className={cn(styles.algoCard, a.id === active && styles.algoCardActive)}
              onClick={() => handleSelect(a.id)}
            >
              <span className={styles.algoName}>{a.question}</span>
              <span className={styles.algoMethod}>{a.name}</span>
            </button>
          ))}
        </div>

        <Card className={styles.resultPanel}>
          <div className={styles.resultHeader}>
            <div>
              <div className={styles.resultTitle}>{algorithm.question}</div>
              <div className={styles.resultSubtitle}>
                <span className={styles.methodTag}>{algorithm.name}</span>
                {algorithm.description}
              </div>
            </div>
            {!algorithm.needsInput && (
              <Button onClick={run} disabled={!canRun || status === "running"} title={canRun ? undefined : "Your role can view results but not start analytics jobs"}>
                {status === "running" ? "Running…" : "Run"}
              </Button>
            )}
          </div>

          {algorithm.needsInput && (
            <div className={styles.inputRow}>
              <input
                className={styles.input}
                placeholder={
                  algorithm.needsInput === "entity" ? "Entity ID, e.g. PRS-0002858" : "Seed entity ID, e.g. ORG-0000150"
                }
                value={entityInput}
                onChange={(e) => setEntityInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && run()}
              />
              <Button onClick={run} disabled={!canRun || status === "running" || !entityInput.trim()} title={canRun ? undefined : "Your role can view results but not start analytics jobs"}>
                {status === "running" ? "Running…" : "Run"}
              </Button>
            </div>
          )}

          {status === "running" && (
            <div className={styles.centerState}>
              <Spinner size={28} />
            </div>
          )}

          {status === "failed" && (
            <EmptyState icon={BarChart3} title="Algorithm failed" description={job.job.data?.error ?? "Unknown error"} />
          )}

          {!job.jobId && (
            <EmptyState
              icon={BarChart3}
              title="No algorithm has run yet"
              description="Pick an algorithm on the left and press Run — results are computed live against the current graph via Neo4j GDS."
            />
          )}

          {status === "done" && projection ? <ProjectionNote projection={projection} /> : null}
          {status === "done" && result && renderResult(active, result)}
        </Card>
      </div>
    </PageShell>
  );
}

function isProjected(value: unknown): value is ProjectedResult<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    "projection" in value &&
    "results" in value
  );
}

/**
 * Which graph produced these numbers, rendered above them.
 *
 * A centrality rank is a statement about a specific graph, and the same
 * algorithm over a different set of relationships gives a different and equally
 * valid answer. Showing the projection is what makes the number interpretable
 * rather than authoritative.
 */
function ProjectionNote({ projection }: { projection: ProjectionProvenance }) {
  return (
    <div className={styles.projectionNote}>
      <div className={styles.projectionHead}>
        <strong>{projection.title}</strong>
        <span className={styles.projectionFingerprint}>{projection.fingerprint}</span>
      </div>
      <p className={styles.projectionDescription}>{projection.description}</p>
      <div className={styles.projectionWeights}>
        {projection.relationships.map((rel) => (
          <span key={rel.type} className={styles.projectionWeight} title={rel.rationale}>
            {rel.type}
            <strong>{rel.weight_property ? `× ${rel.weight_property}` : `× ${rel.weight}`}</strong>
          </span>
        ))}
      </div>
      {projection.caveats.map((caveat) => (
        <p key={caveat} className={styles.projectionCaveat}>
          {caveat}
        </p>
      ))}
    </div>
  );
}

function renderResult(algorithm: AlgorithmId, result: AnyResult) {
  if (algorithm === "pagerank" || algorithm === "betweenness") {
    const rows = result as RankedEntity[];
    const maxScore = Math.max(...rows.map((r) => r.score), 1);
    const columns: TableColumn<RankedEntity>[] = [
      {
        key: "entity",
        header: "Entity",
        render: (row) => (
          <Link href={`/entities/${row.id}`} className={styles.entityLink}>
            {row.name}
          </Link>
        ),
      },
      { key: "type", header: "Type", render: (row) => <span className={styles.labelTag}>{row.label}</span> },
      {
        key: "score",
        header: "Score",
        render: (row) => (
          <div className={styles.scoreBarTrack}>
            <div className={styles.scoreBarFill} style={{ width: `${(row.score / maxScore) * 100}%` }} />
          </div>
        ),
      },
    ];
    return <Table columns={columns} rows={rows} getRowKey={(row) => row.account_id} />;
  }

  if (algorithm === "louvain") {
    const { communities, total_communities } = result as { communities: Community[]; total_communities: number };
    return (
      <div>
        <p className={styles.resultSubtitle} style={{ marginBottom: "var(--space-3)" }}>
          {total_communities} communities found, ranked by how many members ARGUS flagged
        </p>
        <div className={styles.communityGrid}>
          {communities.slice(0, 24).map((c) => (
            <div key={c.community_id} className={styles.communityCard}>
              <div className={styles.communityMeta}>
                <span>Community {c.community_id}</span>
                <span>{c.size} members</span>
              </div>
              <div>
                Top entity:{" "}
                <Link href={`/entities/${c.top_entity.id}`} className={styles.entityLink}>
                  {c.top_entity.name}
                </Link>
              </div>
              <div className={styles.communityMeta}>
                <span>Flagged by ARGUS</span>
                <span>
                  {c.flagged_members} of {c.assessed_members} assessed
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (algorithm === "similar") {
    const rows = result as SimilarEntity[];
    const columns: TableColumn<SimilarEntity>[] = [
      {
        key: "entity",
        header: "Entity",
        render: (row) => (
          <Link href={`/entities/${row.id}`} className={styles.entityLink}>
            {row.name}
          </Link>
        ),
      },
      { key: "type", header: "Type", render: (row) => <span className={styles.labelTag}>{row.label}</span> },
      { key: "similarity", header: "Similarity", render: (row) => `${(row.similarity * 100).toFixed(1)}%` },
    ];
    return <Table columns={columns} rows={rows} getRowKey={(row) => row.id} />;
  }

  if (algorithm === "risk-propagation") {
    const { seeds, propagated } = result as RiskPropagationResult;
    const rows = propagated.slice(0, 50);
    const columns: TableColumn<(typeof rows)[number]>[] = [
      {
        key: "entity",
        header: "Entity",
        render: (row) =>
          row.id ? (
            <Link href={`/entities/${row.id}`} className={styles.entityLink}>
              {row.name}
            </Link>
          ) : (
            row.name
          ),
      },
      { key: "type", header: "Type", render: (row) => <span className={styles.labelTag}>{row.label}</span> },
      { key: "risk", header: "Propagated risk", render: (row) => row.propagated_risk },
    ];
    return (
      <div>
        <p className={styles.resultSubtitle} style={{ marginBottom: "var(--space-3)" }}>
          Seeded from {seeds.map((s) => s.name).join(", ")}
        </p>
        <Table columns={columns} rows={rows} getRowKey={(row) => row.id ?? `${row.name}-${rows.indexOf(row)}`} />
      </div>
    );
  }

  if (algorithm === "anomalies") {
    const rows = result as TransactionAnomaly[];
    if (rows.length === 0) {
      return (
        <EmptyState
          icon={BarChart3}
          title="No anomalies found"
          description="No account's transaction burst pattern was flagged by both Isolation Forest and the z-score baseline."
        />
      );
    }
    const columns: TableColumn<TransactionAnomaly>[] = [
      {
        key: "entity",
        header: "Entity",
        render: (row) => (
          <Link href={`/entities/${row.id}`} className={styles.entityLink}>
            {row.name}
          </Link>
        ),
      },
      { key: "type", header: "Type", render: (row) => <span className={styles.labelTag}>{row.label}</span> },
      { key: "burst", header: "Burst", render: (row) => `${row.max_burst_count} tx in ${row.burst_window_hours}h` },
      {
        key: "baseline",
        header: "Baseline",
        render: (row) => <span className={styles.labelTag}>μ={row.burst_baseline_mean}, σ={row.burst_baseline_std}</span>,
      },
      { key: "zscore", header: "Z-score", render: (row) => `${row.z_score}σ` },
    ];
    return <Table columns={columns} rows={rows} getRowKey={(row) => row.account_id} />;
  }

  const cycles = result as Cycle[];
  if (cycles.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No cycles found"
        description="No flagged circular money-movement paths of length 3–6 exist in the current graph."
      />
    );
  }
  return (
    <div className={styles.communityGrid}>
      {cycles.map((cycle, i) => (
        <div key={i} className={styles.cycleCard}>
          <div className={styles.communityMeta}>
            <span>{cycle.length}-hop cycle</span>
            <span>₹{cycle.total_amount.toLocaleString("en-IN")}</span>
          </div>
          <div className={styles.cycleChain}>
            {cycle.members.map((m, idx) => (
              <span key={idx}>
                <Link href={`/entities/${m.id}`} className={styles.entityLink}>
                  {m.name}
                </Link>
                {idx < cycle.members.length - 1 && <span className={styles.cycleArrow}> → </span>}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
