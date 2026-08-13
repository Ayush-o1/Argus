"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Skeleton } from "@/components/ui/Skeleton";
import { IncidentFeed } from "@/components/dashboard/IncidentFeed";
import { LeadContext } from "@/components/dashboard/LeadContext";
import { LeadQueue } from "@/components/dashboard/LeadQueue";
import { RegionStrip } from "@/components/dashboard/RegionStrip";
import { SituationBrief } from "@/components/dashboard/SituationBrief";
import { PageShell } from "@/components/layout/PageShell";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useBrowseEntities } from "@/hooks/useEntities";
import { useMapRegions } from "@/hooks/useMap";
import type { GraphNode } from "@/lib/types";
import styles from "./page.module.css";

// Leads are drawn from both labels. The previous queue asked only for Persons,
// which silently excluded every elevated Organization — the label carrying the
// shell-company and corporate-network findings.
const LEAD_TYPES = ["Person", "Organization"];
const LEAD_RISK_FLOOR = 1;
const MAX_LEADS = 25;

export default function DashboardPage() {
  const { data: summary, isLoading } = useDashboardSummary();
  const { data: regions } = useMapRegions();
  const { data: allLeads, isFetching: loadingLeads } = useBrowseEntities(LEAD_TYPES, LEAD_RISK_FLOOR);

  const [region, setRegion] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const leads = useMemo(
    () => (region ? allLeads.filter((l) => l.properties.region === region) : allLeads).slice(0, MAX_LEADS),
    [allLeads, region],
  );

  // The context panel is never an empty column: the selection falls back to the
  // top of the queue. Derived rather than synced in an effect — a region filter
  // that drops the current selection resolves on the same render, with no
  // intermediate frame showing a stale or absent lead.
  const selected: GraphNode | null =
    leads.find((l) => l.id === selectedId) ?? leads[0] ?? null;

  if (isLoading || !summary) {
    return (
      <PageShell title="Command Center" subtitle="Global situation and what to investigate next">
        <div className={styles.stack}>
          <Skeleton height={168} />
          <Skeleton height={92} />
          <Skeleton height={420} />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Command Center" subtitle="Global situation and what to investigate next">
      <div className={styles.stack}>
        <SituationBrief summary={summary} regions={regions} />

        {regions && regions.length > 0 ? (
          <RegionStrip regions={regions} selected={region} onSelect={setRegion} />
        ) : null}

        {/* Queue and context are one workspace, not two panels: the list is the
            selector, the panel is the argument for acting on the selection. */}
        <section className={styles.workspace} aria-label="Investigation leads">
          <div className={styles.queueColumn}>
            <header className={styles.columnHead}>
              <span className={styles.columnTitle}>Leads</span>
              <span className={styles.columnMeta}>
                {region ? `${leads.length} in ${region}` : `${leads.length} ranked`}
              </span>
            </header>
            <LeadQueue
              leads={leads}
              isLoading={loadingLeads && allLeads.length === 0}
              selectedId={selected?.id ?? null}
              onSelect={(lead) => setSelectedId(lead.id)}
              emptyLabel={
                region
                  ? `No entity in ${region} currently carries an elevated risk score.`
                  : "No entities currently carry an elevated risk score."
              }
            />
          </div>

          <div className={styles.contextColumn}>
            <LeadContext lead={selected} />
          </div>
        </section>

        <section className={styles.activity} aria-label="Recent activity">
          <header className={styles.columnHead}>
            <span className={styles.columnTitle}>Recent incidents</span>
            <Link href="/alerts" className={styles.columnLink}>
              Triage queue →
            </Link>
          </header>
          <IncidentFeed incidents={summary.recent_incidents} />
        </section>
      </div>
    </PageShell>
  );
}
