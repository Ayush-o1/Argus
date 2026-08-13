"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { useAlerts, useReviewAlert } from "@/hooks/useAlerts";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import type { Incident } from "@/lib/types";
import styles from "./page.module.css";

const SEVERITY_TABS = ["All", "Critical", "High"];
const STATUS_TABS = ["All", "Open", "UnderInvestigation", "Closed"];

const SEVERITY_TONE: Record<Incident["severity"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

const STATUS_LABEL: Record<string, string> = {
  Open: "Open",
  UnderInvestigation: "Under Investigation",
  Closed: "Closed",
};

const SEVERITY_RANK: Record<Incident["severity"], number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
};

export default function AlertsPage() {
  return (
    <Suspense fallback={<PageShell title="Alerts" subtitle="System-detected anomalies awaiting review">{null}</PageShell>}>
      <AlertsPageInner />
    </Suspense>
  );
}

function AlertsPageInner() {
  const searchParams = useSearchParams();
  const [severityTab, setSeverityTab] = useState(() => searchParams.get("severity") ?? "All");
  const [statusTab, setStatusTab] = useState(() => searchParams.get("status") ?? "All");

  const { data, isLoading } = useAlerts(
    statusTab === "All" ? undefined : statusTab,
    severityTab === "All" ? undefined : severityTab,
  );
  const reviewAlert = useReviewAlert();

  // The API only sorts by timestamp — for a triage surface, severity should
  // decide order first (what needs attention), recency second, so a Critical
  // alert doesn't get buried under a page of more-recent Medium ones.
  const alerts = useMemo(
    () => [...(data?.data ?? [])].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]),
    [data],
  );

  return (
    <PageShell title="Alerts" subtitle="System-detected anomalies awaiting review">
      <div className={styles.filterRow}>
        <Tabs tabs={SEVERITY_TABS} active={severityTab} onChange={setSeverityTab} />
        <Tabs tabs={STATUS_TABS} active={statusTab} onChange={setStatusTab} />
      </div>

      {isLoading ? (
        <div className={styles.list}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} height={96} />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <EmptyState icon={AlertTriangle} title="No alerts" description="Nothing matches this filter." />
      ) : (
        <div className={styles.list}>
          {alerts.map((alert) => {
            const status = alert.status ?? "Open";
            return (
              <div key={alert.incident_id} className={styles.alertCard}>
                <div className={styles.topRow}>
                  <div className={styles.leftGroup}>
                    <Badge tone={SEVERITY_TONE[alert.severity]}>{alert.severity}</Badge>
                    <span className={styles.type}>{alert.type.replace(/([A-Z])/g, " $1").trim()}</span>
                  </div>
                  <span className={styles.time}>{formatRelativeTime(alert.timestamp)}</span>
                </div>

                <p className={styles.description}>{alert.description}</p>

                {alert.involved_entities && alert.involved_entities.length > 0 && (
                  <div className={styles.entityChips}>
                    {alert.involved_entities.map((entity, i) => {
                      const id = entityId(entity.label, entity.properties);
                      const name = entityName(entity.label, entity.properties);
                      return id ? (
                        <Link key={i} href={`/entities/${id}`} className={styles.chip}>
                          {name}
                        </Link>
                      ) : (
                        <span key={i} className={styles.chip}>
                          {name}
                        </span>
                      );
                    })}
                  </div>
                )}

                <div className={styles.bottomRow}>
                  <Badge tone="neutral">{STATUS_LABEL[status] ?? status}</Badge>
                  <div style={{ display: "flex", gap: "var(--space-2)" }}>
                    {status === "Open" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={reviewAlert.isPending}
                        onClick={() => reviewAlert.mutate({ alertId: alert.incident_id, status: "UnderInvestigation" })}
                      >
                        Investigate
                      </Button>
                    )}
                    {status !== "Closed" && (
                      <Button
                        size="sm"
                        disabled={reviewAlert.isPending}
                        onClick={() => reviewAlert.mutate({ alertId: alert.incident_id, status: "Closed" })}
                      >
                        Close
                      </Button>
                    )}
                    {status === "Closed" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={reviewAlert.isPending}
                        onClick={() => reviewAlert.mutate({ alertId: alert.incident_id, status: "Open" })}
                      >
                        Reopen
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </PageShell>
  );
}
