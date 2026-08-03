"use client";

import { BarChart3 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import {
  type Community,
  type Cycle,
  type RankedEntity,
  type RiskPropagationResult,
  type SimilarEntity,
  useAnalyticsJob,
} from "@/hooks/useAnalytics";
import styles from "./page.module.css";

type AlgorithmId = "pagerank" | "betweenness" | "louvain" | "similar" | "risk-propagation" | "cycle-detection";

interface AlgorithmDef {
  id: AlgorithmId;
  name: string;
  description: string;
  needsInput?: "entity" | "seeds";
}

const ALGORITHMS: AlgorithmDef[] = [
  {
    id: "pagerank",
    name: "PageRank",
    description: "Globally influential entities — importance amplified by connections to other important entities.",
  },
  {
    id: "betweenness",
    name: "Betweenness Centrality",
    description: "Bridge entities connecting otherwise disconnected groups. High score = key connector.",
  },
  {
    id: "louvain",
    name: "Louvain Communities",
    description: "Partitions the transaction network into densely connected clusters, ranked by average risk.",
  },
  {
    id: "similar",
    name: "Similar Entities",
    description: "Node2Vec graph embeddings + cosine similarity — entities in a structurally similar role.",
    needsInput: "entity",
  },
  {
    id: "risk-propagation",
    name: "Risk Propagation",
    description: "Spreads risk from a seed entity across the network, attenuating by hop distance.",
    needsInput: "seeds",
  },
  {
    id: "cycle-detection",
    name: "Cycle Detection",
    description: "Circular money-movement paths (A → B → ... → A) — the classic laundering-ring signature.",
  },
];

type AnyResult = RankedEntity[] | { communities: Community[]; total_communities: number } | SimilarEntity[] | RiskPropagationResult | Cycle[];

export default function AnalyticsPage() {
  const [active, setActive] = useState<AlgorithmId>("pagerank");
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
  const result = job.job.data?.result;

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
              className={[styles.algoCard, a.id === active && styles.algoCardActive].filter(Boolean).join(" ")}
              onClick={() => handleSelect(a.id)}
            >
              <span className={styles.algoName}>{a.name}</span>
              <span className={styles.algoDesc}>{a.description}</span>
            </button>
          ))}
        </div>

        <Card className={styles.resultPanel}>
          <div className={styles.resultHeader}>
            <div>
              <div className={styles.resultTitle}>{algorithm.name}</div>
              <div className={styles.resultSubtitle}>{algorithm.description}</div>
            </div>
            {!algorithm.needsInput && (
              <Button onClick={run} disabled={status === "running"}>
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
              <Button onClick={run} disabled={status === "running" || !entityInput.trim()}>
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

          {status === "done" && result && renderResult(active, result)}
        </Card>
      </div>
    </PageShell>
  );
}

function renderResult(algorithm: AlgorithmId, result: AnyResult) {
  if (algorithm === "pagerank" || algorithm === "betweenness") {
    const rows = result as RankedEntity[];
    const maxScore = Math.max(...rows.map((r) => r.score), 1);
    return (
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Entity</th>
            <th>Type</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.account_id}>
              <td>
                <Link href={`/entities/${row.id}`} className={styles.entityLink}>
                  {row.name}
                </Link>
              </td>
              <td className={styles.labelTag}>{row.label}</td>
              <td>
                <div className={styles.scoreBarTrack}>
                  <div className={styles.scoreBarFill} style={{ width: `${(row.score / maxScore) * 100}%` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (algorithm === "louvain") {
    const { communities, total_communities } = result as { communities: Community[]; total_communities: number };
    return (
      <div>
        <p className={styles.resultSubtitle} style={{ marginBottom: "var(--space-3)" }}>
          {total_communities} communities found, ranked by average risk
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
                <span>Avg risk</span>
                <span>{c.avg_risk_score}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (algorithm === "similar") {
    const rows = result as SimilarEntity[];
    return (
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Entity</th>
            <th>Type</th>
            <th>Similarity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${row.id}-${i}`}>
              <td>
                <Link href={`/entities/${row.id}`} className={styles.entityLink}>
                  {row.name}
                </Link>
              </td>
              <td className={styles.labelTag}>{row.label}</td>
              <td>{(row.similarity * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (algorithm === "risk-propagation") {
    const { seeds, propagated } = result as RiskPropagationResult;
    return (
      <div>
        <p className={styles.resultSubtitle} style={{ marginBottom: "var(--space-3)" }}>
          Seeded from {seeds.map((s) => s.name).join(", ")}
        </p>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Entity</th>
              <th>Type</th>
              <th>Propagated risk</th>
            </tr>
          </thead>
          <tbody>
            {propagated.slice(0, 50).map((row, i) => (
              <tr key={`${row.id}-${i}`}>
                <td>
                  {row.id ? (
                    <Link href={`/entities/${row.id}`} className={styles.entityLink}>
                      {row.name}
                    </Link>
                  ) : (
                    row.name
                  )}
                </td>
                <td className={styles.labelTag}>{row.label}</td>
                <td>{row.propagated_risk}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
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
