"use client";

import Link from "next/link";
import { bandLabel, formatScore } from "@/lib/assessment";
import { Globe2, MapPin, ShieldHalf, Waypoints } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useRelatedAlerts } from "@/hooks/useAlerts";
import { coverageLabel } from "@/lib/aggregate";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import { RISK_COLOR_UNKNOWN, RISK_COLORS, assessmentTier } from "@/lib/theme";
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
  onSelect: (alert: Incident) => void;
  onReview: (status: "UnderInvestigation" | "Closed") => void;
  isReviewing: boolean;
}

export function AlertDetail({ alert, onSelect, onReview, isReviewing }: AlertDetailProps) {
  // A bounded preview for the list below — never the basis for a count.
  const entities = useMemo(() => alert.involved_entities ?? [], [alert]);

  // Computed by the backend across every involved entity. Deriving it here from
  // `entities` understated the reach of any alert involving more than five
  // (audit B-04): on this dataset that misreported 2 of 9 alerts, one of them
  // as 4 countries when the truth was 6.
  const spread = alert.spread;
  const coverage = alert.involved_coverage;
  const previewLabel = coverage ? coverageLabel(coverage) : null;

  // Two alerts are related when they were planted by the same storyline, which
  // is a real link in the graph — not a heuristic over matching text. Resolved
  // server-side so the answer does not depend on which page is loaded.
  const { data: related = [] } = useRelatedAlerts(alert.incident_id);

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
      {spread && spread.country_count > 0 ? (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>Spread</h4>
          <div className={styles.spread}>
            <span className={styles.spreadItem}>
              <Globe2 size={13} />
              {spread.country_count === 1
                ? spread.countries[0]
                : `${spread.country_count} countries · ${spread.countries.join(", ")}${
                    spread.country_count > spread.countries.length ? ", …" : ""
                  }`}
            </span>
            {spread.region_count > 1 ? (
              <span className={styles.crossRegion}>Crosses {spread.region_count} regions</span>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className={styles.section}>
        {/* The heading counts every involved entity; the list below shows as
            many as fit. Previously both were the preview length, so an alert
            involving thirty entities read "Affected (5)". */}
        <h4 className={styles.sectionTitle}>
          Affected ({spread?.involved_total ?? entities.length})
          {previewLabel ? <span className={styles.sectionNote}> showing {previewLabel}</span> : null}
        </h4>
        <ul className={styles.entities}>
          {entities.map((e, i) => {
            const id = entityId(e.label, e.properties);
            const name = entityName(e.label, e.properties);
            const p = e.properties as Record<string, unknown>;
            // ARGUS's own band, carried on the node by the assessment
            // projection. The previous line read `risk_score` — the generator's
            // planted number — and drew it beside each involved entity as
            // though the alert had been triaged against it.
            const band = typeof p.argus_band === "string" ? p.argus_band : null;
            const score = typeof p.argus_score === "number" ? p.argus_score : null;
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
                <span
                  className={styles.entityRisk}
                  style={{ color: TIER_COLOR[assessmentTier(band)] }}
                  title={bandLabel(band)}
                >
                  {formatScore(score) ?? "—"}
                </span>
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

/** assessmentTier() returns lowercase keys; RISK_COLORS is keyed by display
 * label. An entity with no assessment gets the unknown grey rather than the
 * "low" slate: not knowing is not the same as knowing it is fine. */
const TIER_COLOR: Record<string, string> = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: RISK_COLORS.Low,
  none: RISK_COLOR_UNKNOWN,
};
