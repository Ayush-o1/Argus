"use client";

import { AlertTriangle, Building2, ShieldHalf, TrendingUp, Users } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { CaseList } from "@/components/dashboard/CaseList";
import { IncidentFeed } from "@/components/dashboard/IncidentFeed";
import { RiskDonut } from "@/components/dashboard/RiskDonut";
import { StatCard } from "@/components/dashboard/StatCard";
import { PageShell } from "@/components/layout/PageShell";
import { useDashboardSummary } from "@/hooks/useDashboard";
import styles from "./page.module.css";

export default function DashboardPage() {
  const { data, isLoading } = useDashboardSummary();

  return (
    <PageShell title="Dashboard" subtitle="Command center overview">
      {isLoading || !data ? (
        <DashboardSkeleton />
      ) : (
        <>
          <div className={styles.statGrid}>
            <StatCard label="Active Cases" value={data.active_cases} icon={ShieldHalf} />
            <StatCard label="Open Alerts" value={data.open_alerts} icon={AlertTriangle} />
            <StatCard label="Avg Risk Score" value={data.avg_risk_score} decimals={1} suffix="/ 100" icon={TrendingUp} />
            <StatCard label="Flagged Entities" value={data.flagged_entities} icon={AlertTriangle} />
            <StatCard label="Persons" value={data.total_persons} icon={Users} />
            <StatCard label="Organizations" value={data.total_organizations} icon={Building2} />
          </div>

          <div className={styles.mainGrid}>
            <div className={styles.column}>
              <Card className={styles.panel}>
                <span className={styles.panelTitle}>Recent Incidents</span>
                <IncidentFeed incidents={data.recent_incidents} />
              </Card>
            </div>
            <div className={styles.column}>
              <Card className={styles.panel}>
                <span className={styles.panelTitle}>Entity Risk Distribution</span>
                <RiskDonut data={data.risk_distribution} />
              </Card>
              <Card className={styles.panel}>
                <span className={styles.panelTitle}>Recent Cases</span>
                <CaseList cases={data.recent_cases} />
              </Card>
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
      <div className={styles.statGrid}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} height={88} />
        ))}
      </div>
      <div className={styles.skeletonGrid}>
        <Skeleton height={220} />
        <Skeleton height={160} />
      </div>
    </div>
  );
}
