"use client";

import { Check, FlaskConical, Loader2, Shapes, Shuffle } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { SelectControl } from "@/components/ui/SelectControl";
import { useToast } from "@/components/ui/Toast";
import { useScenarioJob, useScenarioTypes } from "@/hooks/useScenario";
import styles from "./page.module.css";

const TYPE_LABELS: Record<string, string> = {
  shell_company_ring: "Shell Company Ring",
  money_routing_network: "Money Routing Network",
  communication_cluster: "Communication Cluster",
  supply_chain_divergence: "Supply Chain Fraud",
  document_forgery_ring: "Document Forgery Ring",
  identity_overlap: "Identity Overlap",
};

const TYPE_DESCRIPTIONS: Record<string, string> = {
  shell_company_ring:
    "New shell companies linked by shared controllers, with circular transaction routing between their accounts.",
  money_routing_network: "Funds routed through a multi-account chain across banks, each hop retaining a small cut.",
  communication_cluster: "A group of individuals with an unusually dense communication pattern over 48 hours.",
  supply_chain_divergence: "Shipments whose logged route diverges from their manifested itinerary.",
  document_forgery_ring: "Documents with issuer/subject inconsistencies suggesting coordinated forgery.",
  identity_overlap: "Individuals sharing a device with its registered owner.",
};

/** Turns the generated output into a starting point rather than a receipt:
 * each storyline has a characteristic signature, and naming it tells the
 * analyst which surface will actually show it. */
const INVESTIGATION_HINT: Record<string, string> = {
  shell_company_ring:
    "Open the graph and look for controllers directing several companies at once — the ring is visible as a hub, not as any single company.",
  money_routing_network:
    "Follow the account chain in the graph. Each hop retains a small cut, so the amounts decay along the path rather than matching end to end.",
  communication_cluster:
    "Check the timeline around the injected window — the cluster shows up as a burst in communication volume, not as any one unusual call.",
  supply_chain_divergence:
    "Open the map with anomalous routes shown. The divergence is geometric: the logged route leaves the corridor its manifest implies.",
  document_forgery_ring:
    "Compare issuer and subject across the new documents — the inconsistency repeats across the set, which is what distinguishes it from a clerical error.",
  identity_overlap:
    "Look for a device with more than one associated person in the graph; the overlap is a shared node, not a shared attribute.",
  anomalous_transaction_burst:
    "Check the timeline for a spike above the flagged-volume baseline, then open the account's own activity to see the burst in detail.",
};

const SEVERITY_TONE: Record<string, "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

export default function ScenarioPage() {
  const { data: typesData } = useScenarioTypes();
  const [type, setType] = useState<string | null>(null);
  const [complexity, setComplexity] = useState("Medium");
  const [seed, setSeed] = useState<number | null>(null);
  const { start, job, jobId, reset } = useScenarioJob();
  const { showToast } = useToast();

  const activeType = type ?? typesData?.types[0] ?? "";
  const status = job.data?.status;

  // Job status arrives via polling, not a mutation callback, so a toast on
  // completion needs its own effect — fired once per job by keying off jobId.
  const notifiedJobRef = useRef<string | null>(null);
  useEffect(() => {
    if (!jobId || !status || status === "running" || notifiedJobRef.current === jobId) return;
    notifiedJobRef.current = jobId;
    if (status === "done") {
      showToast("Scenario generated successfully", "success");
    } else if (status === "failed") {
      showToast(job.data?.error ?? "Scenario generation failed", "error");
    }
  }, [jobId, status, job.data?.error, showToast]);

  function randomizeSeed() {
    setSeed(Math.floor(Math.random() * 1_000_000));
  }

  function handleGenerate() {
    reset();
    start.mutate({ type: activeType, complexity, seed });
  }

  const stages = job.data?.stages ?? [];
  const result = job.data?.result;

  return (
    <PageShell
      title="Scenario Generator"
      subtitle="Create a new synthetic investigation scenario on demand — runs the real generation engine against the live graph"
    >
      <div className={styles.layout}>
        <Card className={styles.form}>
          <div className={styles.field}>
            <span className={styles.fieldLabel}>Storyline Type</span>
            <SelectControl
              icon={Shapes}
              value={activeType}
              onChange={(e) => setType(e.target.value)}
              aria-label="Storyline type"
              options={(typesData?.types ?? []).map((t) => ({ value: t, label: TYPE_LABELS[t] ?? t }))}
            />
            <p className={styles.typeDescription}>{TYPE_DESCRIPTIONS[activeType]}</p>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>Complexity</span>
            <SegmentedControl
              segments={(typesData?.complexities ?? ["Low", "Medium", "High"]).map((c) => ({ value: c, label: c }))}
              value={complexity}
              onChange={setComplexity}
              ariaLabel="Complexity"
            />
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>Seed</span>
            <div className={styles.seedRow}>
              <input
                className={styles.input}
                type="number"
                placeholder="Random"
                value={seed ?? ""}
                onChange={(e) => setSeed(e.target.value ? Number(e.target.value) : null)}
              />
              <Button variant="secondary" size="md" onClick={randomizeSeed} aria-label="Randomize seed">
                <Shuffle size={16} />
              </Button>
            </div>
          </div>

          <Button onClick={handleGenerate} disabled={!activeType || status === "running"}>
            {status === "running" ? "Generating…" : "Generate Scenario"}
          </Button>
        </Card>

        <Card className={styles.resultPanel}>
          {!jobId && (
            <EmptyState
              icon={FlaskConical}
              title="No scenario generated yet"
              description="Pick a storyline type and press Generate — this creates real new entities and writes them into the live graph."
            />
          )}

          {status === "running" && (
            <div className={styles.stageList}>
              {stages.map((stage, i) => (
                <div key={i} className={styles.stageRow}>
                  <Check size={14} color="var(--risk-low)" />
                  {stage}
                </div>
              ))}
              <div className={styles.stageRow}>
                <Loader2 size={14} style={{ animation: "argus-spin 0.9s linear infinite" }} />
                Working…
              </div>
            </div>
          )}

          {status === "failed" && (
            <EmptyState
              icon={FlaskConical}
              title="Generation failed"
              description={job.data?.error ?? "Unknown error"}
              actions={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Try Again
                </Button>
              }
            />
          )}

          {status === "done" && result && (
            <>
              <div className={styles.resultHeader}>
                <div className={styles.resultTitle}>{TYPE_LABELS[result.type] ?? result.type}</div>
                <Badge tone={SEVERITY_TONE[result.severity]}>{result.severity}</Badge>
              </div>
              <p className={styles.resultDescription}>{result.description}</p>

              {INVESTIGATION_HINT[result.type] ? (
                <div className={styles.hint}>
                  <span className={styles.hintLabel}>What to look for</span>
                  <p className={styles.hintBody}>{INVESTIGATION_HINT[result.type]}</p>
                </div>
              ) : null}

              <div className={styles.countsGrid}>
                {Object.entries(result.node_counts)
                  .filter(([, count]) => count > 0)
                  .map(([label, count]) => (
                    <div key={label} className={styles.countCard}>
                      <span className={styles.countValue}>{count}</span>
                      <span className={styles.countLabel}>{label}</span>
                    </div>
                  ))}
              </div>

              <div className={styles.resultActions}>
                <Link href={`/graph?seed=${result.key_entity_id}`}>
                  <Button variant="secondary" size="sm">
                    Open in Graph
                  </Button>
                </Link>
                {result.case_id && (
                  <Link href={`/cases/${result.case_id}`}>
                    <Button variant="secondary" size="sm">
                      Open Case
                    </Button>
                  </Link>
                )}
                <Link href={`/entities/${result.key_entity_id}`}>
                  <Button size="sm">Key Entity: {result.key_entity_name}</Button>
                </Link>
              </div>
            </>
          )}
        </Card>
      </div>
    </PageShell>
  );
}
