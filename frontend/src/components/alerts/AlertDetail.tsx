"use client";

import Link from "next/link";
import { Globe2, MapPin, ShieldHalf, Waypoints } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import { RISK_COLORS, riskTier } from "@/lib/theme";
import type { Incident } from "@/lib/types";
import styles from "./AlertDetail.module.css";

/**
 * The analytical case for an alert, not a formatted copy of its record.
 *
 * Triage needs six answers before an analyst can decide: what happened, why it
 * matters, what is affected, where, when, and what it connects to. Everything
 * below is derived from the incident payload — its involved entities carry
 * their own risk scores and geography, and `storyline_id` is what makes two
 * alerts genuinely related rather than merely similar-looking.
 */

const SEVERITY_TONE: Record<Incident["severity"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

/** Incident types are stored PascalCase; the queue already splits them, and the
 * detail heading showing "FinancialCrime" beside a queue row reading "Financial
 * Crime" reads as two different things. */
function formatAlertType(type: string): string {
  return type.replace(/([A-Z])/g, " $1").trim();
}

const STATUS_LABEL: Record<string, string> = {
  Open: "Open",
  UnderInvestigation: "Investigating",
  Closed: "Closed",
};

interface AlertDetailProps {
  alert: Incident;
  allAlerts: Incident[];
  onSelect: (alert: Incident) => void;
  onReview: (status: "UnderInvestigation" | "Closed") => void;
  isReviewing: boolean;
}

export function AlertDetail({ alert, allAlerts, onSelect, onReview, isReviewing }: AlertDetailProps) {
  // Memoised so the `??` default doesn't produce a new array identity on every
  // render and re-run the spread calculation below.
  const entities = useMemo(() => alert.involved_entities ?? [], [alert]);

  const spread = useMemo(() => {
    const countries = new Set<string>();
    const regions = new Set<string>();
    let peakRisk = 0;
    for (const e of entities) {
      const p = e.properties as Record<string, unknown>;
      if (typeof p.country === "string") countries.add(p.country);
      if (typeof p.region === "string") regions.add(p.region);
      if (typeof p.risk_score === "number") peakRisk = Math.max(peakRisk, p.risk_score);
    }
    return { countries: [...countries], regions: [...regions], peakRisk };
  }, [entities]);

  // Two alerts are related when they were planted by the same storyline, which
  // is a real link in the graph — not a heuristic over matching text.
  const related = useMemo(
    () =>
      alert.storyline_id
        ? allAlerts.filter((a) => a.storyline_id === alert.storyline_id && a.incident_id !== alert.incident_id)
        : [],
    [allAlerts, alert],
  );

  const firstEntityId = entities.map((e) => entityId(e.label, e.properties)).find(Boolean);
  const mappable = entities.find(
    (e) => (e.properties as Record<string, unknown>).lat != null && entityId(e.label, e.properties),
  );

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.identity}>
          <div className={styles.badges}>
            <Badge tone={SEVERITY_TONE[alert.severity]}>{alert.severity}</Badge>
            <span className={styles.status}>{STATUS_LABEL[alert.status ?? "Open"] ?? alert.status}</span>
          </div>
          <h3 className={styles.title}>{formatAlertType(alert.type)}</h3>
          <p className={styles.meta}>
            {alert.incident_id} · {formatRelativeTime(alert.timestamp)}
          </p>
        </div>
      </header>

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Signal</h4>
        <p className={styles.description}>{alert.description}</p>
      </section>

      {/* Geographic spread is the answer to "where", computed from the entities
          the incident actually involves. In a dataset spanning 50 countries,
          an alert touching several is a materially different finding from one
          confined to a single city. */}
      {spread.countries.length > 0 ? (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>Spread</h4>
          <div className={styles.spread}>
            <span className={styles.spreadItem}>
              <Globe2 size={13} />
              {spread.countries.length === 1
                ? spread.countries[0]
                : `${spread.countries.length} countries · ${spread.countries.join(", ")}`}
            </span>
            {spread.regions.length > 1 ? (
              <span className={styles.crossRegion}>Crosses {spread.regions.length} regions</span>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>Affected ({entities.length})</h4>
        <ul className={styles.entities}>
          {entities.map((e, i) => {
            const id = entityId(e.label, e.properties);
            const name = entityName(e.label, e.properties);
            const p = e.properties as Record<string, unknown>;
            const risk = typeof p.risk_score === "number" ? p.risk_score : 0;
            const place = [p.city ?? p.registered_city, p.country].filter(Boolean).join(", ");
            const body = (
              <>
                <span className={styles.entityIcon}>
                  <EntityTypeIcon label={e.label} size={14} />
                </span>
                <span className={styles.entityBody}>
                  <span className={styles.entityName}>{name}</span>
                  <span className={styles.entityMeta}>
                    {e.label}
                    {place ? ` · ${place}` : ""}
                  </span>
                </span>
                {risk > 0 ? (
                  <span className={styles.entityRisk} style={{ color: RISK_COLORS[riskLabel(risk)] }}>
                    {Math.round(risk)}
                  </span>
                ) : null}
              </>
            );
            return (
              <li key={id ?? `${e.label}-${i}`}>
                {id ? (
                  <Link href={`/entities/${id}`} className={styles.entityRow}>
                    {body}
                  </Link>
                ) : (
                  <div className={styles.entityRowStatic}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {related.length > 0 ? (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>Related alerts ({related.length})</h4>
          <p className={styles.relatedHint}>Planted by the same storyline — treat as one investigation.</p>
          <ul className={styles.related}>
            {related.map((r) => (
              <li key={r.incident_id}>
                <button type="button" className={styles.relatedRow} onClick={() => onSelect(r)}>
                  <ShieldHalf size={13} />
                  <span className={styles.relatedTitle}>{formatAlertType(r.type)}</span>
                  <span className={styles.relatedMeta}>{formatRelativeTime(r.timestamp)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className={styles.actions}>
        {alert.status !== "UnderInvestigation" ? (
          <Button size="sm" onClick={() => onReview("UnderInvestigation")} disabled={isReviewing}>
            Investigate
          </Button>
        ) : null}
        {firstEntityId ? (
          <Link href={`/graph?seed=${firstEntityId}`}>
            <Button variant="secondary" size="sm">
              <Waypoints size={14} /> Graph
            </Button>
          </Link>
        ) : null}
        {mappable ? (
          <Link href={`/map?focus=${entityId(mappable.label, mappable.properties)}`}>
            <Button variant="secondary" size="sm">
              <MapPin size={14} /> Map
            </Button>
          </Link>
        ) : null}
        {alert.status !== "Closed" ? (
          <Button variant="ghost" size="sm" onClick={() => onReview("Closed")} disabled={isReviewing}>
            Close
          </Button>
        ) : null}
      </footer>
    </div>
  );
}

/** riskTier() returns lowercase keys; RISK_COLORS is keyed by display label. */
function riskLabel(score: number): "Critical" | "High" | "Medium" | "Low" {
  const map = {
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
    none: "Low",
  } as const;
  return map[riskTier(score)];
}
