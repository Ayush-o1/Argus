"use client";

import { AlertTriangle, FileSearch, Info, ShieldHalf } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAlerts } from "@/hooks/useAlerts";
import { useCases } from "@/hooks/useCases";
import { useInvestigations } from "@/hooks/useInvestigations";
import { PRIORITY_TONE, RULE_LABEL, STATE_LABEL, STATE_TONE, formatPriority } from "@/lib/alerts";
import { CASE_STATUS_LABEL, CASE_STATUS_TONE } from "@/lib/caseLabels";
import { describeState } from "@/lib/investigations";
import { NEXT_MODE_PATH } from "@/lib/next/modeRouting";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import styles from "./TriageQueues.module.css";

const ALERT_ROWS_SHOWN = 15;
const CASE_ROWS_SHOWN = 10;

/**
 * Triage mode: Alerts and the investigation queue as working queues, with
 * Cases kept visibly separate — mirroring the real `/investigations` and
 * `/cases` pages' own framing (see their doc comments) rather than inventing
 * a softer distinction for this build. Opening an alert or investigation
 * calls the shared scope bus's `openAlert`/`openInvestigation` (which focus
 * the subject and switch the Graph lens) and then navigates to Investigate —
 * the same two-step every "jump to Investigate" action in Command uses.
 *
 * Live-wired (Phase 12): `useAlerts`/`useInvestigations`/`useCases` are the
 * real hooks the `/alerts`/`/investigations`/`/cases` pages use. Alerts are
 * scoped to `state: "open"` and capped to the top `ALERT_ROWS_SHOWN` by
 * priority — this is a compact triage surface, not the full filterable
 * `/alerts` table, and the count shown is always the true total from the
 * API's own `meta`, not the length of what's rendered.
 */
export function TriageQueues() {
  const router = useRouter();
  const openAlert = useNextScopeStore((s) => s.openAlert);
  const openInvestigation = useNextScopeStore((s) => s.openInvestigation);

  const { data: alertsEnvelope, isLoading: alertsLoading } = useAlerts({ state: "open" });
  const { data: investigationsEnvelope, isLoading: investigationsLoading } = useInvestigations();
  const { data: casesEnvelope, isLoading: casesLoading } = useCases();

  const alertsTotal = alertsEnvelope?.meta?.total ?? 0;
  const alerts = [...(alertsEnvelope?.data ?? [])].sort((a, b) => b.priority - a.priority).slice(0, ALERT_ROWS_SHOWN);
  const investigations = investigationsEnvelope?.data ?? [];
  const casesTotal = casesEnvelope?.meta?.total ?? 0;
  const cases = [...(casesEnvelope?.data ?? [])]
    .sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime())
    .slice(0, CASE_ROWS_SHOWN);

  function goInvestigate() {
    router.push(NEXT_MODE_PATH.investigate);
  }

  return (
    <div className={styles.wrap}>
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Alerts ({alerts.length}
          {alertsTotal > alerts.length ? ` of ${alertsTotal}` : ""})
        </h2>
        {alertsLoading ? (
          <Skeleton height={120} />
        ) : alerts.length === 0 ? (
          <EmptyState icon={AlertTriangle} title="No open alerts" description="Either no rule has fired, or no run has happened yet." />
        ) : (
          <ul className={styles.list}>
            {alerts.map((alert) => (
              <li key={alert.alert_key}>
                <button
                  type="button"
                  className={styles.row}
                  onClick={() => {
                    openAlert(alert.alert_key, alert.scope[0] ?? null);
                    goInvestigate();
                  }}
                >
                  <div className={styles.rowHead}>
                    <Badge tone={PRIORITY_TONE[alert.priority_band]}>
                      {alert.priority_band} · {formatPriority(alert.priority)}
                    </Badge>
                    <Badge tone={STATE_TONE[alert.state]}>{STATE_LABEL[alert.state]}</Badge>
                    <span className={styles.rule}>{RULE_LABEL[alert.rule_id] ?? alert.rule_id}</span>
                    {alert.occurrence_count > 1 ? <span className={styles.meta}>seen {alert.occurrence_count}×</span> : null}
                  </div>
                  <p className={styles.title}>{alert.title}</p>
                  <p className={styles.summary}>{alert.summary}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Investigations ({investigations.length})</h2>
        {investigationsLoading ? (
          <Skeleton height={80} />
        ) : investigations.length === 0 ? (
          <EmptyState
            icon={FileSearch}
            title="No investigations yet"
            description="Investigations are opened from the alert queue. Nothing here is pre-populated."
          />
        ) : (
          <ul className={styles.list}>
            {investigations.map((inv) => (
              <li key={inv.investigation_id}>
                <button
                  type="button"
                  className={styles.row}
                  onClick={() => {
                    openInvestigation(inv.inv_ref, null);
                    goInvestigate();
                  }}
                >
                  <div className={styles.rowHead}>
                    <span className={styles.ref}>{inv.inv_ref}</span>
                    <Badge tone={inv.state === "closed" ? "neutral" : "accent"}>{describeState(inv.state, inv.outcome)}</Badge>
                    <span className={styles.meta}>confidence {inv.confidence}</span>
                    {inv.dissenting_reviews > 0 ? <span className={styles.dissent}>reviewer disagrees</span> : null}
                  </div>
                  <p className={styles.title}>{inv.title}</p>
                  <p className={styles.meta}>
                    {inv.alert_count} alert{inv.alert_count === 1 ? "" : "s"} · {inv.finding_count} finding
                    {inv.finding_count === 1 ? "" : "s"} · {inv.assigned_to ? `assigned to ${inv.assigned_to}` : "unassigned"}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Cases ({cases.length}
          {casesTotal > cases.length ? ` of ${casesTotal}` : ""})
        </h2>
        <div className={styles.provenanceNote}>
          <Info size={15} aria-hidden />
          <span>
            These records come from a registered source and are shown as reported. They are not investigations opened in this
            deployment, and nothing here has been concluded by an analyst.
          </span>
        </div>
        {casesLoading ? (
          <Skeleton height={100} />
        ) : cases.length === 0 ? (
          <EmptyState icon={ShieldHalf} title="No cases" description="No source case records match this filter." />
        ) : (
          <ul className={styles.list}>
            {cases.map((c) => (
              <li key={c.case_id} className={styles.caseRow}>
                <span className={styles.ref}>{c.case_id}</span>
                <Badge tone={CASE_STATUS_TONE[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge>
                <span className={styles.title}>{c.title}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
