"use client";

import { AlertTriangle, Ban, Database, Play, RotateCcw, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { SourceReliabilityBadge } from "@/components/provenance/RatingBadge";
import { SyntheticBadge } from "@/components/provenance/KindBadge";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import {
  freshness,
  useIngestFailures,
  useIngestHealth,
  useReleaseConnector,
  useReplayFailure,
  useRunConnector,
} from "@/hooks/useIngest";
import { STAGE_MEANING } from "@/lib/ingest";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./page.module.css";

/**
 * Source health — the page that answers "is anything still arriving?".
 *
 * The question matters because its failure mode is silent. A feed that stops
 * looks exactly like a world in which nothing is happening: the analyst sees no
 * new reports and concludes there is nothing to report. Every element here
 * exists to make that difference visible, so the design leads with freshness
 * and rejected records rather than with throughput, which is the number that
 * looks healthiest while telling you least.
 */
export default function SourcesPage() {
  const { data: health, isLoading } = useIngestHealth();
  const { data: failures } = useIngestFailures();
  const { data: session } = useSession();
  const [selected, setSelected] = useState<string | null>(null);

  const canManage = session?.permissions.includes("ingest:manage") ?? false;
  const canSeePayload = session?.permissions.includes("entity:read") ?? false;

  const run = useRunConnector();
  const release = useReleaseConnector();
  const replay = useReplayFailure();

  if (isLoading) {
    return (
      <PageShell title="Sources" subtitle="Feed health and rejected records">
        <Skeleton height={200} />
      </PageShell>
    );
  }

  const connectors = health?.connectors ?? [];
  const stale = health?.stale ?? [];
  const openFailures = failures ?? [];

  return (
    <PageShell
      title="Sources"
      subtitle="Where ARGUS's data comes from, whether it is still arriving, and what was rejected"
    >
      {/* A source that has gone quiet is the finding, not a footnote, so it
          leads the page rather than sitting in a column of a table. */}
      {stale.length > 0 ? (
        <div className={styles.alertBanner}>
          <ShieldAlert size={18} />
          <div>
            <strong>
              {stale.length} source{stale.length === 1 ? " is" : "s are"} not reporting
            </strong>
            <p className={styles.alertBody}>
              A silent feed is indistinguishable from a quiet world. Until this is resolved, an
              absence of reports from {stale.length === 1 ? "this source" : "these sources"} cannot
              be read as an absence of activity.
            </p>
            <ul className={styles.staleList}>
              {stale.map((s) => (
                <li key={s.connector_id}>
                  <strong>{s.display_name}</strong>{" "}
                  <span className={styles.staleId}>({s.connector_id})</span> — {s.reason}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {connectors.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No sources configured"
          description={
            "Nothing is feeding ARGUS yet. Everything currently in the graph came from the " +
            "scenario generator, which is registered as a synthetic source — see any entity's " +
            "Provenance tab. A real feed is added by registering a source and a connector; no " +
            "code change is required."
          }
        />
      ) : (
        <div className={styles.grid}>
          {connectors.map((connector) => {
            const fresh = freshness(connector);
            const failureRate =
              connector.records_24h > 0
                ? connector.failed_records_24h / connector.records_24h
                : 0;
            return (
              <Card key={connector.connector_id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <div>
                    <div className={styles.cardTitle}>{connector.display_name}</div>
                    <div className={styles.cardMeta}>
                      {connector.source_name} · {connector.connector_type}
                    </div>
                  </div>
                  <div className={styles.badges}>
                    <SourceReliabilityBadge reliability={connector.source_reliability} />
                    {connector.source_is_synthetic ? <SyntheticBadge /> : null}
                  </div>
                </div>

                {connector.quarantine_reason ? (
                  <div className={styles.quarantine}>
                    <Ban size={14} />
                    <span>{connector.quarantine_reason}</span>
                  </div>
                ) : null}

                <div className={styles.stats}>
                  <Stat label="Last produced" value={fresh.label} tone={fresh.tone} />
                  <Stat
                    label="Records (24h)"
                    value={connector.records_24h.toLocaleString()}
                    hint={`${connector.new_24h.toLocaleString()} new`}
                  />
                  <Stat
                    label="Rejected (24h)"
                    value={connector.failed_records_24h.toLocaleString()}
                    tone={failureRate > 0.1 ? "critical" : failureRate > 0 ? "medium" : "ok"}
                    hint={
                      connector.records_24h > 0
                        ? `${(failureRate * 100).toFixed(0)}% of ${connector.records_24h.toLocaleString()}`
                        : "no records"
                    }
                  />
                  <Stat
                    label="Open in DLQ"
                    value={connector.open_failures.toLocaleString()}
                    tone={connector.open_failures > 0 ? "medium" : "ok"}
                  />
                </div>

                {canManage ? (
                  <div className={styles.actions}>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => run.mutate(connector.connector_id)}
                      disabled={run.isPending || !!connector.quarantined_at}
                    >
                      <Play size={13} /> Run now
                    </Button>
                    {connector.quarantined_at ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => release.mutate(connector.connector_id)}
                        disabled={release.isPending}
                      >
                        <RotateCcw size={13} /> Release
                      </Button>
                    ) : null}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setSelected(selected === connector.connector_id ? null : connector.connector_id)
                      }
                    >
                      {selected === connector.connector_id ? "Hide" : "Rejected records"}
                    </Button>
                  </div>
                ) : null}

                {selected === connector.connector_id ? (
                  <FailureList
                    failures={openFailures.filter((f) => f.connector_id === connector.connector_id)}
                    canReplay={canManage && canSeePayload}
                    onReplay={(id) => replay.mutate(id)}
                    pending={replay.isPending}
                  />
                ) : null}
              </Card>
            );
          })}
        </div>
      )}

      {health?.queue && Object.keys(health.queue).length > 0 ? (
        <Card className={styles.queueCard}>
          <div className={styles.cardTitle}>Job queue</div>
          <p className={styles.cardMeta}>
            Ingestion runs as durable queued work rather than in-process tasks, so a restart
            postpones a batch instead of losing it.
          </p>
          <div className={styles.queueRow}>
            {Object.entries(health.queue).map(([status, count]) => (
              <Badge key={status} tone={status === "dead" ? "critical" : "neutral"}>
                {status}: {count}
              </Badge>
            ))}
          </div>
          {(health.queue.dead ?? 0) > 0 ? (
            <p className={styles.deadNote}>
              <AlertTriangle size={13} /> Buried jobs exhausted their retries. They are kept rather
              than discarded so the failure stays countable.
            </p>
          ) : null}
        </Card>
      ) : null}
    </PageShell>
  );
}

function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "medium" | "critical" | "neutral";
}) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${styles[tone]}`}>{value}</span>
      {hint ? <span className={styles.statHint}>{hint}</span> : null}
    </div>
  );
}

function FailureList({
  failures,
  canReplay,
  onReplay,
  pending,
}: {
  failures: { failure_id: number; stage: keyof typeof STAGE_MEANING; error_detail: string; occurred_at: string; replay_count: number }[];
  canReplay: boolean;
  onReplay: (id: number) => void;
  pending: boolean;
}) {
  if (failures.length === 0) {
    return <p className={styles.noFailures}>No rejected records outstanding.</p>;
  }
  return (
    <div className={styles.failures}>
      {failures.map((failure) => (
        <div key={failure.failure_id} className={styles.failure}>
          <div className={styles.failureTop}>
            <Badge tone="high">{failure.stage}</Badge>
            <span className={styles.failureTime}>{formatTimestamp(failure.occurred_at)}</span>
            {canReplay ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onReplay(failure.failure_id)}
                disabled={pending}
              >
                Replay
              </Button>
            ) : null}
          </div>
          <p className={styles.failureStage}>{STAGE_MEANING[failure.stage]}</p>
          <p className={styles.failureDetail}>{failure.error_detail}</p>
          {failure.replay_count > 0 ? (
            <span className={styles.failureTime}>Replayed {failure.replay_count}×</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
