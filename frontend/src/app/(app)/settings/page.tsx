"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { PageShell } from "@/components/layout/PageShell";
import { useDashboardSummary } from "@/hooks/useDashboard";
import styles from "./page.module.css";

const TABS = ["Data", "Appearance", "Performance", "About"];

export default function SettingsPage() {
  const [tab, setTab] = useState("Data");
  const { data: summary, isLoading } = useDashboardSummary();

  return (
    <PageShell title="Settings" subtitle="System configuration and about this instance">
      <div className={styles.layout}>
        <Tabs tabs={TABS} active={tab} onChange={setTab} />

        {tab === "Data" && (
          <Card>
            <div className={styles.sectionTitle}>Current World</div>
            {isLoading ? (
              <Skeleton height={80} />
            ) : (
              <div className={styles.grid}>
                <div className={styles.statCard}>
                  <span className={styles.statValue}>{summary?.total_persons ?? "—"}</span>
                  <span className={styles.statLabel}>Persons</span>
                </div>
                <div className={styles.statCard}>
                  <span className={styles.statValue}>{summary?.total_organizations ?? "—"}</span>
                  <span className={styles.statLabel}>Organizations</span>
                </div>
                <div className={styles.statCard}>
                  <span className={styles.statValue}>{summary?.total_transactions ?? "—"}</span>
                  <span className={styles.statLabel}>Transactions</span>
                </div>
                <div className={styles.statCard}>
                  <span className={styles.statValue}>{summary?.flagged_entities ?? "—"}</span>
                  <span className={styles.statLabel}>Flagged Entities</span>
                </div>
              </div>
            )}
            <p className={styles.paragraph} style={{ marginTop: "var(--space-4)" }}>
              This world is deterministic and reproducible — the same seed always produces the same graph. New
              scenarios can be layered on top at any time from the Scenario Generator without disturbing this
              baseline. To regenerate the entire world from scratch with a new seed, run:
            </p>
            <div className={styles.codeBlock}>python3 generate_world.py --seed 42</div>
            <p className={styles.paragraph} style={{ marginTop: "var(--space-3)" }}>
              from the <code>generator/</code> directory. This wipes and rebuilds the full graph — there is no
              in-app control for this deliberately destructive operation.
            </p>
          </Card>
        )}

        {tab === "Appearance" && (
          <Card>
            <div className={styles.sectionTitle}>Appearance</div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Theme</span>
              <span>Dark (fixed by design)</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Accent color</span>
              <span>Blue #3D7BFF</span>
            </div>
            <p className={styles.paragraph} style={{ marginTop: "var(--space-3)" }}>
              ARGUS is designed dark-mode-first for command-center legibility — an analyst staring at a graph
              canvas for hours benefits from a low-glare, high-contrast surface. A light theme isn&apos;t planned.
            </p>
          </Card>
        )}

        {tab === "Performance" && (
          <Card>
            <div className={styles.sectionTitle}>Performance Thresholds</div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Max Graph Explorer neighborhood size</span>
              <span>500 nodes</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Timeline flagged-activity limit</span>
              <span>500 items</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Timeline baseline sample size</span>
              <span>300 items</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Analytics job poll interval</span>
              <span>1.2s</span>
            </div>
            <p className={styles.paragraph} style={{ marginTop: "var(--space-3)" }}>
              These are fixed in the backend (not user-configurable) — they bound query cost on a single-machine
              deployment rather than tune a multi-tenant service.
            </p>
          </Card>
        )}

        {tab === "About" && (
          <Card>
            <div className={styles.sectionTitle}>About ARGUS</div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Version</span>
              <span>0.1.0</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowLabel}>Stack</span>
              <span>Next.js 16 · FastAPI · Neo4j + GDS · Redis</span>
            </div>
            <p className={styles.paragraph} style={{ marginTop: "var(--space-4)" }}>
              ARGUS is a portfolio engineering project. It is set in real Indian geography, but every person,
              organization, phone number, account, transaction, and document inside it is 100% synthetic and
              procedurally generated. No real individual or company is represented. There is no scraping, no
              OSINT, and no real surveillance functionality of any kind — this is a demonstration of graph
              analytics, investigation-workflow design, and connected data visualization.
            </p>
            <p className={styles.paragraph} style={{ marginTop: "var(--space-3)" }}>
              See <code>ARGUS_PLAN.md</code> in the repository root for the full architecture and design
              rationale.
            </p>
          </Card>
        )}
      </div>
    </PageShell>
  );
}
