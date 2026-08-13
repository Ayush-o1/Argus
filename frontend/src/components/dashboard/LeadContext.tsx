"use client";

import Link from "next/link";
import { Clock, MapPin, ShieldHalf, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { RiskBadge, riskLevelFromScore } from "@/components/ui/RiskBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useEntity, useEntityAlerts, useEntityCases } from "@/hooks/useEntities";
import { formatRelativeTime } from "@/lib/formatters";
import type { GraphNode } from "@/lib/types";
import styles from "./LeadContext.module.css";

/**
 * The case for pursuing the selected lead.
 *
 * This is the panel that answers "why am I seeing this?" — the question a
 * ranked list of risk scores cannot. Everything shown is drawn from the graph:
 * the scorer's own recorded factors, the entity's real connection counts, and
 * the alerts and cases that already reference it. Nothing is inferred or
 * invented to fill the panel out.
 */
export function LeadContext({ lead }: { lead: GraphNode | null }) {
  const entityId = lead?.id ?? "";
  // The list payload already carries risk_factors and geography, so the detail
  // fetch is only needed for connection counts — the panel renders useful
  // content immediately and fills in the rest.
  const { data: detail } = useEntity(entityId);
  const { data: alerts } = useEntityAlerts(entityId);
  const { data: cases } = useEntityCases(entityId);

  if (!lead) {
    return (
      <div className={styles.placeholder}>
        <Waypoints size={22} />
        <p>Select a lead to see why it surfaced and where to take it.</p>
      </div>
    );
  }

  const p = lead.properties;
  const factors: string[] = p.risk_factors ?? [];
  const place = [p.city ?? p.registered_city, p.country].filter(Boolean).join(", ");
  const connections = detail?.connections ?? {};
  const connectionEntries = Object.entries(connections).filter(([, n]) => n > 0);

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.identity}>
          <h3 className={styles.name}>{lead.name}</h3>
          <p className={styles.subtitle}>
            {lead.label} · {lead.id}
            {place ? ` · ${place}` : ""}
            {p.region ? ` · ${p.region}` : ""}
          </p>
        </div>
        <RiskBadge level={riskLevelFromScore(lead.risk_score)} />
      </header>

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Why it surfaced</h4>
        {factors.length > 0 ? (
          <ul className={styles.factors}>
            {factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>
            Scored {Math.round(lead.risk_score)} with no individual factors recorded against it.
          </p>
        )}
      </section>

      {(alerts?.length ?? 0) > 0 || (cases?.length ?? 0) > 0 ? (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>Already referenced</h4>
          <ul className={styles.refs}>
            {(alerts ?? []).slice(0, 3).map((alert) => (
              <li key={alert.incident_id}>
                <Link href={`/alerts?focus=${alert.incident_id}`} className={styles.refRow}>
                  <ShieldHalf size={13} />
                  <span className={styles.refTitle}>{alert.type}</span>
                  <span className={styles.refMeta}>{formatRelativeTime(alert.timestamp)}</span>
                </Link>
              </li>
            ))}
            {(cases ?? []).slice(0, 3).map((c) => (
              <li key={c.case_id}>
                <Link href={`/cases/${c.case_id}`} className={styles.refRow}>
                  <Waypoints size={13} />
                  <span className={styles.refTitle}>{c.title}</span>
                  <span className={styles.refMeta}>{c.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Connections</h4>
        {detail ? (
          connectionEntries.length > 0 ? (
            <ul className={styles.connections}>
              {connectionEntries.map(([label, count]) => (
                <li key={label} className={styles.connection}>
                  <span>{label}</span>
                  <span className={styles.connectionCount}>{count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted}>No connected entities recorded.</p>
          )
        ) : (
          <Skeleton height={44} />
        )}
      </section>

      <footer className={styles.actions}>
        <Link href={`/entities/${lead.id}`}>
          <Button size="sm">Open profile</Button>
        </Link>
        <Link href={`/graph?seed=${lead.id}`}>
          <Button variant="secondary" size="sm">
            <Waypoints size={14} /> Graph
          </Button>
        </Link>
        {p.lat != null && p.lng != null ? (
          <Link href={`/map?focus=${lead.id}`}>
            <Button variant="secondary" size="sm">
              <MapPin size={14} /> Map
            </Button>
          </Link>
        ) : null}
        <Link href="/timeline">
          <Button variant="secondary" size="sm">
            <Clock size={14} /> Timeline
          </Button>
        </Link>
      </footer>
    </div>
  );
}
