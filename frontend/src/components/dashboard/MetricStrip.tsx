import Link from "next/link";
import { cn } from "@/lib/cn";
import { formatCompactNumber } from "@/lib/formatters";
import type { DashboardSummary } from "@/lib/types";
import styles from "./MetricStrip.module.css";

interface MetricProps {
  label: string;
  value: string;
  suffix?: string;
  href?: string;
  tone?: "critical" | "high" | "neutral";
}

function Metric({ label, value, suffix, href, tone = "neutral" }: MetricProps) {
  const body = (
    <>
      <span className={styles.label}>{label}</span>
      <span className={styles.valueRow}>
        <span
          className={cn(
            styles.value,
            tone === "critical" && styles.valueCritical,
            tone === "high" && styles.valueHigh,
          )}
        >
          {value}
        </span>
        {suffix ? <span className={styles.suffix}>{suffix}</span> : null}
      </span>
    </>
  );

  return href ? (
    <Link href={href} className={cn(styles.metric, styles.metricLink)}>
      {body}
    </Link>
  ) : (
    <div className={styles.metric}>{body}</div>
  );
}

export function MetricStrip({ summary }: { summary: DashboardSummary }) {
  const elevated = summary.elevated_entities;
  const unassessable =
    summary.assessment_distribution.find((b) => b.band === "insufficient_evidence")?.count ?? 0;
  const unassessed =
    summary.assessment_distribution.find((b) => b.band === "unassessed")?.count ?? 0;

  return (
    <div className={styles.strip}>
      <Metric
        label="Open alerts"
        value={String(summary.open_alerts)}
        href="/alerts"
        tone={summary.open_alerts > 0 ? "critical" : "neutral"}
      />
      <Metric
        label="Elevated entities"
        value={String(elevated)}
        suffix={`of ${formatCompactNumber(summary.assessed_persons)} assessed`}
        href="/assessment"
        tone={elevated > 0 ? "high" : "neutral"}
      />
      <Metric label="Active cases" value={String(summary.active_cases)} href="/cases" />
      {/* Not a risk figure. The count of people ARGUS could not reach a view
          on — the honest companion to the one above, and deliberately the same
          size, because a queue of 27 means something different when 2,700
          people were never assessable. */}
      <Metric
        label="Not assessable"
        value={formatCompactNumber(unassessable + unassessed)}
        suffix="too little evidence"
        href="/assessment"
      />

      <div className={styles.context}>
        <span className={styles.contextRow}>
          <span className={styles.contextValue}>{formatCompactNumber(summary.total_persons)}</span> persons
        </span>
        <span className={styles.contextRow}>
          <span className={styles.contextValue}>{formatCompactNumber(summary.total_organizations)}</span> organizations
        </span>
        <span className={styles.contextRow}>
          <span className={styles.contextValue}>{formatCompactNumber(summary.total_transactions)}</span> transactions
        </span>
      </div>
    </div>
  );
}
