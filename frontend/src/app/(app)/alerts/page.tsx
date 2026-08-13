"use client";

import { AlertTriangle, Waypoints } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl, type Segment } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAlerts, useReviewAlert } from "@/hooks/useAlerts";
import { cn } from "@/lib/cn";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import { RISK_COLORS } from "@/lib/theme";
import type { Incident } from "@/lib/types";
import styles from "./page.module.css";

type SeverityFilter = "All" | "Critical" | "High";
type StatusFilter = "All" | "Open" | "UnderInvestigation" | "Closed";

const SEVERITY_TONE: Record<Incident["severity"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

const SEVERITY_COLOR: Record<Incident["severity"], string> = {
  Critical: RISK_COLORS.Critical,
  High: RISK_COLORS.High,
  Medium: RISK_COLORS.Medium,
  Low: RISK_COLORS.Low,
};

const STATUS_LABEL: Record<string, string> = {
  Open: "Open",
  UnderInvestigation: "Investigating",
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
    <Suspense fallback={<PageShell title="Alerts" subtitle="Triage queue">{null}</PageShell>}>
      <AlertsPageInner />
    </Suspense>
  );
}

function AlertsPageInner() {
  const searchParams = useSearchParams();
  const [severity, setSeverity] = useState<SeverityFilter>(
    () => (searchParams.get("severity") as SeverityFilter) ?? "All",
  );
  const [status, setStatus] = useState<StatusFilter>(() => (searchParams.get("status") as StatusFilter) ?? "All");

  const { data, isLoading } = useAlerts(status === "All" ? undefined : status, severity === "All" ? undefined : severity);
  const reviewAlert = useReviewAlert();

  // The API only sorts by timestamp — for a triage surface, severity should
  // decide order first (what needs attention), recency second, so a Critical
  // alert doesn't get buried under a page of more-recent Medium ones.
  const alerts = useMemo(
    () =>
      [...(data?.data ?? [])].sort(
        (a, b) =>
          SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      ),
    [data],
  );

  const severitySegments: Segment<SeverityFilter>[] = [
    { value: "All", label: "All severities" },
    { value: "Critical", label: "Critical" },
    { value: "High", label: "High" },
  ];
  const statusSegments: Segment<StatusFilter>[] = [
    { value: "All", label: "All" },
    { value: "Open", label: "Open" },
    { value: "UnderInvestigation", label: "Investigating" },
    { value: "Closed", label: "Closed" },
  ];

  return (
    <PageShell
      title="Alerts"
      subtitle="System-detected anomalies, most severe first — triage, investigate, or close"
    >
      <div className={styles.filterRow}>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>Severity</span>
          <SegmentedControl segments={severitySegments} value={severity} onChange={setSeverity} ariaLabel="Filter by severity" />
        </div>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>Status</span>
          <SegmentedControl segments={statusSegments} value={status} onChange={setStatus} ariaLabel="Filter by status" />
        </div>
      </div>

      {isLoading ? (
        <div className={styles.list}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height={92} />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className={styles.emptyWrap}>
          <EmptyState
            icon={AlertTriangle}
            title="Queue clear"
            description="No alerts match this filter. Try widening the severity or status filter."
          />
        </div>
      ) : (
        <div className={styles.list}>
          {alerts.map((alert) => {
            const alertStatus = alert.status ?? "Open";
            const isClosed = alertStatus === "Closed";
            const entities = alert.involved_entities ?? [];
            const firstId = entities.map((e) => entityId(e.label, e.properties)).find(Boolean);

            return (
              <div
                key={alert.incident_id}
                className={cn(styles.alertCard, isClosed && styles.resolved)}
                style={{ ["--severity-color" as string]: SEVERITY_COLOR[alert.severity] }}
              >
                <div className={styles.head}>
                  <Badge tone={SEVERITY_TONE[alert.severity]}>{alert.severity}</Badge>
                  <span className={styles.type}>{alert.type.replace(/([A-Z])/g, " $1").trim()}</span>
                  <Badge tone={isClosed ? "ok" : "neutral"}>{STATUS_LABEL[alertStatus] ?? alertStatus}</Badge>
                  <span className={styles.time}>{formatRelativeTime(alert.timestamp)}</span>
                </div>

                {/* Investigate leads. Closing an alert is the dismissive path
                    and must not out-rank it visually — it previously rendered
                    as the filled primary button on every open alert. */}
                <div className={styles.actions}>
                  {firstId ? (
                    <Link href={`/graph?seed=${firstId}`}>
                      <Button size="sm" variant="secondary" title="Open the involved entities in the Graph Explorer">
                        <Waypoints size={13} /> Graph
                      </Button>
                    </Link>
                  ) : null}
                  {alertStatus === "Open" && (
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={reviewAlert.isPending}
                      onClick={() => reviewAlert.mutate({ alertId: alert.incident_id, status: "UnderInvestigation" })}
                    >
                      Investigate
                    </Button>
                  )}
                  {!isClosed && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={reviewAlert.isPending}
                      onClick={() => reviewAlert.mutate({ alertId: alert.incident_id, status: "Closed" })}
                    >
                      Close
                    </Button>
                  )}
                  {isClosed && (
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

                <p className={styles.description}>{alert.description}</p>

                {entities.length > 0 && (
                  <div className={styles.entityChips}>
                    <span className={styles.chipLabel}>Involves</span>
                    {entities.map((entity, i) => {
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
              </div>
            );
          })}
        </div>
      )}
    </PageShell>
  );
}
