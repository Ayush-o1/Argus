"use client";

import { ArrowLeftRight, Calendar, Phone, Waypoints } from "lucide-react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { RiskScoreWidget } from "@/components/entity/RiskScoreWidget";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { PageShell } from "@/components/layout/PageShell";
import { useEntity, useEntityTimeline } from "@/hooks/useEntities";
import { formatRelativeTime } from "@/lib/formatters";
import type { TimelineItem } from "@/lib/types";
import styles from "./page.module.css";

const DISPLAY_FIELDS: Record<string, { key: string; label: string }[]> = {
  Person: [
    { key: "occupation", label: "Occupation" },
    { key: "dob", label: "Date of Birth" },
    { key: "gender", label: "Gender" },
    { key: "nationality", label: "Nationality" },
    { key: "city", label: "City" },
    { key: "state", label: "State" },
    { key: "phone", label: "Phone" },
    { key: "status", label: "Status" },
  ],
  Organization: [
    { key: "type", label: "Type" },
    { key: "industry", label: "Industry" },
    { key: "registered_city", label: "Registered City" },
    { key: "state", label: "State" },
    { key: "registration_date", label: "Registration Date" },
    { key: "status", label: "Status" },
  ],
  Vehicle: [
    { key: "type", label: "Type" },
    { key: "make", label: "Make" },
    { key: "model", label: "Model" },
    { key: "color", label: "Color" },
    { key: "plate", label: "Plate" },
  ],
  Account: [
    { key: "bank", label: "Bank" },
    { key: "type", label: "Type" },
    { key: "balance_class", label: "Balance Class" },
    { key: "status", label: "Status" },
    { key: "opened_date", label: "Opened" },
  ],
};

const TIMELINE_ICON: Record<TimelineItem["kind"], typeof Calendar> = {
  Event: Calendar,
  Transaction: ArrowLeftRight,
  Communication: Phone,
};

export default function EntityProfilePage() {
  const params = useParams<{ id: string }>();
  const entityId = params.id;
  const [tab, setTab] = useState("Properties");

  const { data: entity, isLoading } = useEntity(entityId);
  const { data: timeline } = useEntityTimeline(entityId);

  if (isLoading) {
    return (
      <PageShell>
        <Skeleton height={80} />
      </PageShell>
    );
  }

  if (!entity) {
    return (
      <PageShell title="Entity Profile" subtitle={entityId}>
        <EmptyState icon={Waypoints} title="Entity not found" description={`No entity with ID ${entityId}.`} />
      </PageShell>
    );
  }

  const fields = DISPLAY_FIELDS[entity.label] ?? [];
  const riskFactors: string[] = entity.properties.risk_factors ?? [];
  const connections = entity.connections ?? {};

  return (
    <PageShell>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <span className={styles.iconWrap}>
            <EntityTypeIcon label={entity.label} size={22} />
          </span>
          <div>
            <div className={styles.name}>{entity.name}</div>
            <div className={styles.subtitle}>
              {entity.label} · {entity.id}
            </div>
          </div>
        </div>
        <div className={styles.actions}>
          <Link href={`/graph?seed=${entity.id}`}>
            <Button variant="secondary" size="sm">
              View in Graph
            </Button>
          </Link>
        </div>
      </div>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <span className={styles.sidebarTitle}>Connections</span>
          {Object.keys(connections).length === 0 ? (
            <span style={{ fontSize: 13, color: "var(--text-tertiary)" }}>No connections yet.</span>
          ) : (
            Object.entries(connections).map(([label, count]) => (
              <div key={label} className={styles.connectionRow}>
                <span>{label}</span>
                <span className={styles.connectionCount}>{count}</span>
              </div>
            ))
          )}
        </aside>

        <div>
          <Tabs tabs={["Properties", "Risk", "Activity"]} active={tab} onChange={setTab} />

          {tab === "Properties" && (
            <Card>
              <div className={styles.propertyGrid}>
                {fields.map(({ key, label }) => (
                  <div key={key} className={styles.propertyRow}>
                    <span className={styles.propertyLabel}>{label}</span>
                    <span className={styles.propertyValue}>{String(entity.properties[key] ?? "—")}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {tab === "Risk" && (
            <Card>
              <RiskScoreWidget score={entity.risk_score} factors={riskFactors} />
            </Card>
          )}

          {tab === "Activity" && (
            <Card>
              {!timeline || timeline.length === 0 ? (
                <EmptyState icon={Calendar} title="No activity" description="No recorded events, transactions, or communications." />
              ) : (
                <div className={styles.timelineList}>
                  {timeline.map((item, i) => {
                    const Icon = TIMELINE_ICON[item.kind];
                    return (
                      <div key={i} className={styles.timelineRow}>
                        <span className={styles.timelineMarker}>
                          <Icon size={15} color="var(--text-secondary)" />
                        </span>
                        <div className={styles.timelineBody}>
                          <div className={styles.timelineTop}>
                            {item.kind}
                            {item.subtype ? ` · ${item.subtype}` : ""}
                          </div>
                          <span className={styles.timelineDetail}>{describeTimelineItem(item)}</span>
                        </div>
                        <span className={styles.timelineTime}>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </PageShell>
  );
}

function describeTimelineItem(item: TimelineItem): string {
  const d = item.details;
  if (item.kind === "Event") return `${d.location ?? ""}, ${d.city ?? ""}`;
  if (item.kind === "Transaction") return `${d.tx_id} · ₹${Number(d.amount).toLocaleString("en-IN")} → ${d.other_account}`;
  if (item.kind === "Communication") return `${d.comm_id} · ${d.duration_seconds}s`;
  return "";
}
