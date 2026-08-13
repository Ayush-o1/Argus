"use client";

import { AlertTriangle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { AlertDetail } from "@/components/alerts/AlertDetail";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl, type Segment } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAlerts, useReviewAlert } from "@/hooks/useAlerts";
import { cn } from "@/lib/cn";
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
  const focusId = searchParams.get("focus");
  const [severity, setSeverity] = useState<SeverityFilter>(
    () => (searchParams.get("severity") as SeverityFilter) ?? "All",
  );
  const [status, setStatus] = useState<StatusFilter>(() => (searchParams.get("status") as StatusFilter) ?? "All");
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  // Derived rather than synced: an incoming ?focus wins until the analyst picks
  // something, and a filter change that drops the selection falls back to the
  // top of the queue on the same render.
  const selected: Incident | null =
    alerts.find((a) => a.incident_id === selectedId) ??
    (focusId ? (alerts.find((a) => a.incident_id === focusId) ?? null) : null) ??
    alerts[0] ??
    null;

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
        <div className={styles.workspace}>
          <Skeleton height={420} />
          <Skeleton height={420} />
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
        // Queue selects, detail argues. A stack of self-contained cards forced
        // every alert to carry its full context inline, so the page could only
        // ever be skimmed — and comparing two alerts meant scrolling between
        // two walls of text.
        <div className={styles.workspace}>
          <div className={styles.queueColumn}>
            <header className={styles.queueHead}>
              <span className={styles.queueTitle}>Queue</span>
              <span className={styles.queueCount}>{alerts.length}</span>
            </header>
            <ul className={styles.queue} role="listbox" aria-label="Alert queue">
              {alerts.map((alert) => {
                const isSelected = alert.incident_id === selected?.incident_id;
                const isClosed = (alert.status ?? "Open") === "Closed";
                return (
                  <li key={alert.incident_id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={cn(styles.queueRow, isSelected && styles.queueRowSelected, isClosed && styles.resolved)}
                      style={{ ["--severity-color" as string]: SEVERITY_COLOR[alert.severity] }}
                      onClick={() => setSelectedId(alert.incident_id)}
                    >
                      <span className={styles.queueTop}>
                        <Badge tone={SEVERITY_TONE[alert.severity]}>{alert.severity}</Badge>
                        <span className={styles.queueTime}>{formatRelativeTime(alert.timestamp)}</span>
                      </span>
                      <span className={styles.queueType}>{alert.type.replace(/([A-Z])/g, " $1").trim()}</span>
                      <span className={styles.queueDesc}>{alert.description}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className={styles.detailColumn}>
            {selected ? (
              <AlertDetail
                alert={selected}
                allAlerts={alerts}
                onSelect={(a) => setSelectedId(a.incident_id)}
                onReview={(next) => reviewAlert.mutate({ alertId: selected.incident_id, status: next })}
                isReviewing={reviewAlert.isPending}
              />
            ) : null}
          </div>
        </div>
      )}
    </PageShell>
  );
}
