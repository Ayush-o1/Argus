import { useDashboardSummary } from "@/hooks/useDashboard";
import { useMapRegions } from "@/hooks/useMap";
import { Skeleton } from "@/components/ui/Skeleton";
import styles from "./SituationBrief.module.css";

const STAMP = new Intl.DateTimeFormat("en-US", { day: "2-digit", month: "short", year: "numeric" });

/**
 * The first thing a session says — a sentence composed from real figures,
 * not a card grid. `useDashboardSummary`/`useMapRegions` are the same hooks
 * the real `/dashboard` page uses — this component was always typed against
 * `DashboardSummary`/`RegionRollup` (the real API shapes), so this is a data
 * source swap, not a rewrite. `useDashboardSummary` itself is gated on
 * `entity:read` (an administrator, by design, does not hold it) — the
 * calling page is responsible for that permission check; this component
 * only handles "still loading" vs "loaded".
 */
export function SituationBrief() {
  const { data: summary, isLoading: summaryLoading } = useDashboardSummary();
  const { data: regions, isLoading: regionsLoading } = useMapRegions();

  if (summaryLoading || regionsLoading || !summary || !regions) {
    return (
      <section className={styles.section} aria-label="Situation brief">
        <Skeleton height={140} />
      </section>
    );
  }

  const now = new Date();
  const active = regions.filter((r) => r.elevated_count > 0);
  const ranked = [...regions].sort((a, b) => b.elevated_count - a.elevated_count);
  const routeLead = [...regions].sort((a, b) => b.flagged_routes - a.flagged_routes)[0];
  const unassessable =
    (summary.assessment_distribution.find((d) => d.band === "insufficient_evidence")?.count ?? 0) +
    (summary.assessment_distribution.find((d) => d.band === "unassessed")?.count ?? 0);

  const figures = [
    { label: "ELEVATED ENTITIES", value: summary.elevated_entities, color: "var(--risk-critical)" },
    { label: "INCIDENTS · 14D", value: summary.incidents_in_window, color: "var(--risk-high)" },
    { label: "OPEN ALERTS", value: summary.open_alerts, color: "var(--text-primary)" },
    { label: "OPEN INVESTIGATIONS", value: summary.open_investigations, color: "var(--text-primary)" },
    { label: "NOT ASSESSABLE", value: unassessable, color: "var(--text-secondary)" },
  ];

  return (
    <section className={styles.section} aria-label="Situation brief">
      <div className={styles.head}>
        <span className={styles.label}>SITUATION BRIEF</span>
        <span className={styles.rule} />
        <span className={styles.stamp}>
          {STAMP.format(now).toUpperCase()} · {String(now.getUTCHours()).padStart(2, "0")}:
          {String(now.getUTCMinutes()).padStart(2, "0")} UTC
        </span>
      </div>
      <p className={styles.prose}>
        ARGUS assessed <strong>{summary.elevated_entities} entities</strong> as warranting review across{" "}
        <strong>{active.length} regions</strong>, concentrated in <strong>{ranked[0]?.region}</strong>.{" "}
        <strong>{summary.open_alerts} alerts</strong> are open, <strong>{summary.high_priority_open_alerts}</strong> of
        them high priority. Flagged routes cluster on <strong>{routeLead?.region}</strong> ({routeLead?.flagged_routes}{" "}
        of them). It could not assess <strong>{unassessable.toLocaleString("en-US")}</strong> subjects, which is not a
        low-risk finding.
      </p>
      <dl className={styles.figures}>
        {figures.map((f) => (
          <div key={f.label} className={styles.figure}>
            <dt className={styles.figureLabel}>{f.label}</dt>
            <dd className={styles.figureValue} style={{ color: f.color }}>
              {f.value.toLocaleString("en-US")}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
