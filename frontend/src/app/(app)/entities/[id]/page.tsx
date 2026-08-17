"use client";

import { ArrowLeftRight, Calendar, Clock, Map as MapIcon, Phone, ShieldHalf, Sparkles, Waypoints } from "lucide-react";
import { AssessmentPanel } from "@/components/entity/AssessmentPanel";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { SourceReportedRisk } from "@/components/entity/SourceReportedRisk";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Skeleton } from "@/components/ui/Skeleton";
import { IdentityNotice } from "@/components/resolution/IdentityNotice";
import { Tabs } from "@/components/ui/Tabs";
import { PageShell } from "@/components/layout/PageShell";
import { useEntity, useEntityAlerts, useEntityCases, useEntityTimeline } from "@/hooks/useEntities";
import { useEntityProvenance } from "@/hooks/useProvenance";
import { useEntitySummary } from "@/hooks/useAssistant";
import { AttributeProvenance } from "@/components/provenance/AttributeProvenance";
import { ConflictPanel } from "@/components/provenance/ConflictPanel";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { formatRelativeTime } from "@/lib/formatters";
import type { CaseSummary, Incident, TimelineItem } from "@/lib/types";
import styles from "./page.module.css";

const DISPLAY_FIELDS: Record<string, { key: string; label: string }[]> = {
  Person: [
    { key: "occupation", label: "Occupation" },
    { key: "dob", label: "Date of Birth" },
    { key: "gender", label: "Gender" },
    { key: "nationality", label: "Nationality" },
    { key: "city", label: "City" },
    { key: "state", label: "State/Province" },
    { key: "country", label: "Country" },
    { key: "region", label: "Region" },
    { key: "phone", label: "Phone" },
    { key: "status", label: "Status" },
  ],
  Organization: [
    { key: "type", label: "Type" },
    { key: "industry", label: "Industry" },
    { key: "registered_city", label: "Registered City" },
    { key: "state", label: "State/Province" },
    { key: "country", label: "Country" },
    { key: "region", label: "Region" },
    { key: "registration_date", label: "Registration Date" },
    { key: "status", label: "Status" },
  ],
  Location: [
    { key: "type", label: "Type" },
    { key: "city", label: "City" },
    { key: "state", label: "State/Province" },
    { key: "country", label: "Country" },
    { key: "region", label: "Region" },
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

const CASE_STATUS_TONE: Record<CaseSummary["status"], "neutral" | "accent" | "high" | "low"> = {
  Draft: "neutral",
  Open: "accent",
  UnderReview: "high",
  Closed: "low",
};

const ALERT_SEVERITY_TONE: Record<Incident["severity"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

export default function EntityProfilePage() {
  const params = useParams<{ id: string }>();
  const entityId = params.id;
  const [tab, setTab] = useState("Properties");

  const { data: entity, isLoading } = useEntity(entityId);
  const { data: timeline } = useEntityTimeline(entityId);
  const { data: relatedCases } = useEntityCases(entityId);
  const { data: relatedAlerts } = useEntityAlerts(entityId);
  const { data: provenance } = useEntityProvenance(entityId);
  const summary = useEntitySummary();

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
  const connections = entity.connections ?? {};
  const p = entity.properties;
  const place = [p.city ?? p.registered_city, p.country].filter(Boolean).join(", ");

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
              {place ? ` · ${place}` : ""}
            </div>
          </div>
          <AssessmentBadge assessment={entity.assessment} />
        </div>
        <div className={styles.actions}>
          <Link href={`/graph?seed=${entity.id}`}>
            <Button variant="secondary" size="sm">
              View in Graph
            </Button>
          </Link>
          {entity.properties.lat != null && entity.properties.lng != null ? (
            <Link href={`/map?focus=${entity.id}`}>
              <Button variant="secondary" size="sm">
                <MapIcon size={14} /> View on Map
              </Button>
            </Link>
          ) : null}
          {timeline && timeline.length > 0 ? (
            <Link href="/timeline">
              <Button variant="secondary" size="sm">
                <Clock size={14} /> Timeline
              </Button>
            </Link>
          ) : null}
        </div>
      </div>

      {/* Whether this record is one of several describing the same entity
          changes how every count below should be read, so it sits above them
          rather than behind a tab. Renders nothing when the record stands
          alone. */}
      <IdentityNotice entityRef={entityId} />

      {/* Whether an entity is already under investigation changes what the
          analyst should do next, so it belongs on arrival rather than three
          clicks into a tab. Only rendered when there is something to say. */}
      {(relatedCases?.length ?? 0) > 0 || (relatedAlerts?.length ?? 0) > 0 ? (
        <button type="button" className={styles.investigationBanner} onClick={() => setTab("Cases & Alerts")}>
          <ShieldHalf size={15} />
          <span>
            Already referenced in{" "}
            {relatedCases && relatedCases.length > 0 ? (
              <strong>
                {relatedCases.length} case{relatedCases.length === 1 ? "" : "s"}
              </strong>
            ) : null}
            {relatedCases?.length && relatedAlerts?.length ? " and " : null}
            {relatedAlerts && relatedAlerts.length > 0 ? (
              <strong>
                {relatedAlerts.length} alert{relatedAlerts.length === 1 ? "" : "s"}
              </strong>
            ) : null}
          </span>
          <span className={styles.bannerAction}>Review →</span>
        </button>
      ) : null}

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          {/* Risk lived behind a tab, so the one attribute that decides whether
              this entity is worth pursuing was invisible on arrival. It is the
              first thing in the sidebar now, and permanently on screen while
              the analyst moves between tabs. */}
          <div className={styles.sidebarBlock}>
            <span className={styles.sidebarTitle}>ARGUS assessment</span>
            <AssessmentPanel subjectRef={entity.id} />
          </div>

          {/* The source's own risk figure, kept and clearly separated.
              Deleting it would destroy a claim the provenance store holds an
              assertion about; promoting it would be the audit's G-08 finding
              all over again. It sits below ARGUS's own assessment, labelled as
              what it is: something a source said. */}
          {provenance?.attributes.risk_score ? (
            <div className={styles.sidebarBlock}>
              <span className={styles.sidebarTitle}>Reported by source</span>
              <SourceReportedRisk provenance={provenance.attributes.risk_score} />
            </div>
          ) : null}

          <span className={styles.sidebarTitle}>Connections</span>
          {Object.keys(connections).length === 0 ? (
            <span style={{ fontSize: 13, color: "var(--text-tertiary)" }}>No connections yet.</span>
          ) : (
            // Each count is a route into the graph rather than a statistic —
            // "9 Persons" is only useful if the analyst can go and see them.
            Object.entries(connections).map(([label, count]) => (
              <Link key={label} href={`/graph?seed=${entity.id}`} className={styles.connectionRow}>
                <span>{label}</span>
                <span className={styles.connectionCount}>{count}</span>
              </Link>
            ))
          )}
        </aside>

        <div>
          <Tabs
            tabs={["Properties", "Activity", "Cases & Alerts", "Provenance", "Summary"]}
            active={tab}
            onChange={setTab}
          />

          {tab === "Properties" && (
            <Card>
              {/* A disagreement about an attribute belongs beside the
                  attributes, not behind another tab — an analyst reading a
                  value needs to know two sources contest it before they act on
                  it, not after. */}
              {provenance && provenance.conflicts.length > 0 ? (
                <div style={{ marginBottom: "var(--space-4)" }}>
                  <ConflictPanel conflicts={provenance.conflicts} />
                </div>
              ) : null}

              <div className={styles.propertyGrid}>
                {fields.map(({ key, label }) => (
                  <div key={key} className={styles.propertyRow}>
                    <span className={styles.propertyLabel}>{label}</span>
                    <span className={styles.propertyValue}>{String(entity.properties[key] ?? "—")}</span>
                    {/* Every displayed value gets its origin one click away.
                        Rendered even when nothing accounts for the value: an
                        unattributed field that looked identical to a sourced
                        one is the exact confusion this phase removes. */}
                    <AttributeProvenance
                      label={label}
                      value={entity.properties[key]}
                      provenance={provenance?.attributes[key]}
                      complete={provenance?.attributes_complete ?? true}
                    />
                  </div>
                ))}
              </div>
            </Card>
          )}

          {tab === "Provenance" && <ProvenancePanel subjectRef={entity.id} />}

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

          {tab === "Cases & Alerts" && (
            <div className={styles.timelineList}>
              <Card>
                <div className={styles.propertyLabel} style={{ marginBottom: "var(--space-3)" }}>
                  CASES
                </div>
                {!relatedCases || relatedCases.length === 0 ? (
                  <EmptyState icon={ShieldHalf} title="No related cases" description="This entity isn't linked to any case." />
                ) : (
                  relatedCases.map((c) => (
                    <Link key={c.case_id} href={`/cases/${c.case_id}`} className={styles.timelineRow}>
                      <div className={styles.timelineBody}>
                        <div className={styles.timelineTop}>{c.title}</div>
                        <span className={styles.timelineDetail}>
                          {c.case_id} · Opened {formatRelativeTime(c.opened_at)}
                        </span>
                      </div>
                      <Badge tone={CASE_STATUS_TONE[c.status]}>{c.status}</Badge>
                    </Link>
                  ))
                )}
              </Card>
              <Card>
                <div className={styles.propertyLabel} style={{ marginBottom: "var(--space-3)" }}>
                  ALERTS
                </div>
                {!relatedAlerts || relatedAlerts.length === 0 ? (
                  <EmptyState icon={Waypoints} title="No related alerts" description="This entity isn't involved in any alert." />
                ) : (
                  relatedAlerts.map((a) => (
                    <Link key={a.incident_id} href="/alerts" className={styles.timelineRow}>
                      <div className={styles.timelineBody}>
                        <div className={styles.timelineTop}>{a.type.replace(/([A-Z])/g, " $1").trim()}</div>
                        <span className={styles.timelineDetail}>{a.description}</span>
                      </div>
                      <Badge tone={ALERT_SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
                    </Link>
                  ))
                )}
              </Card>
            </div>
          )}

          {tab === "Summary" && (
            <Card>
              {summary.data ? (
                <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text-secondary)" }}>{summary.data.summary}</p>
              ) : (
                <EmptyState
                  icon={Sparkles}
                  title="No summary generated yet"
                  description="A deterministic template composer turns this entity's risk factors and connections into analyst-brief prose — no LLM involved."
                  actions={
                    <Button size="sm" onClick={() => summary.mutate(entity.id)} disabled={summary.isPending}>
                      {summary.isPending ? <Spinner size={16} /> : "Generate Summary"}
                    </Button>
                  }
                />
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
