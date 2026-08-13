"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { CaseList } from "@/components/dashboard/CaseList";
import { IncidentFeed } from "@/components/dashboard/IncidentFeed";
import { MetricStrip } from "@/components/dashboard/MetricStrip";
import { PriorityQueue } from "@/components/dashboard/PriorityQueue";
import { RiskDonut } from "@/components/dashboard/RiskDonut";
import { PageShell } from "@/components/layout/PageShell";
import { useDashboardSummary } from "@/hooks/useDashboard";
import styles from "./page.module.css";

interface PanelProps {
  title: string;
  hint?: string;
  href?: string;
  linkLabel?: string;
  flush?: boolean;
  children: ReactNode;
}

function Panel({ title, hint, href, linkLabel = "View all", flush, children }: PanelProps) {
  return (
    <Card className={styles.panel}>
      <div className={styles.panelHead}>
        <div className={styles.panelTitleGroup}>
          <span className={styles.panelTitle}>{title}</span>
          {hint ? <span className={styles.panelHint}>{hint}</span> : null}
        </div>
        {href ? (
          <Link href={href} className={styles.panelLink}>
            {linkLabel} →
          </Link>
        ) : null}
      </div>
      <div className={flush ? styles.panelBodyFlush : styles.panelBody}>{children}</div>
    </Card>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useDashboardSummary();

  return (
    <PageShell title="Command Center" subtitle="What needs attention across the synthetic world right now">
      {isLoading || !data ? (
        <DashboardSkeleton />
      ) : (
        <>
          <MetricStrip summary={data} />

          <div className={styles.mainGrid}>
            <div className={styles.column}>
              <Panel
                title="Priority queue"
                hint="Highest-risk entities — start here"
                href="/search"
                linkLabel="Browse all"
              >
                <PriorityQueue />
              </Panel>
              <Panel
                title="Recent incidents"
                hint="System-detected activity, newest first"
                href="/alerts"
                flush
              >
                <IncidentFeed incidents={data.recent_incidents} />
              </Panel>
            </div>

            <div className={styles.column}>
              <Panel title="Risk distribution" hint="Population by severity band" flush>
                <RiskDonut data={data.risk_distribution} />
              </Panel>
              <Panel title="Active cases" hint="Open investigations" href="/cases" flush>
                <CaseList cases={data.recent_cases} />
              </Panel>
            </div>
          </div>
        </>
      )}
    </PageShell>
  );
}

function DashboardSkeleton() {
  return (
    <div>
      <Skeleton height={92} />
      <div className={styles.skeletonGrid} style={{ marginTop: "var(--space-5)" }}>
        <Skeleton height={260} />
        <Skeleton height={200} />
      </div>
    </div>
  );
}
