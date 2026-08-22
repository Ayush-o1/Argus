"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Gavel,
  Link2,
  ScrollText,
  ShieldAlert,
  UserCheck,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { useInvestigation, useInvestigationHistory } from "@/hooks/useInvestigations";
import { describeState, findingStanding } from "@/lib/investigations";
import styles from "./page.module.css";

type Tab = "work" | "evidence" | "history";

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * One investigation, and everything that was concluded in it.
 *
 * Three things on this page are deliberate and easy to get wrong:
 *
 *  - **Withdrawn and superseded findings are shown, greyed.** A findings list
 *    that quietly drops the retracted half reads as though the conclusion was
 *    obvious from the start.
 *  - **Detached evidence is shown, with who removed it and why.** That a piece
 *    of evidence was once thought to belong is part of how the conclusion was
 *    reached (audit G-11).
 *  - **A dissenting review sits beside the outcome, not instead of it.** The
 *    reviewer does not overwrite the analyst; both are on the record.
 */
export default function InvestigationDetailPage() {
  const params = useParams<{ ref: string }>();
  const ref = params?.ref;
  const [tab, setTab] = useState<Tab>("work");
  const { data, isLoading } = useInvestigation(ref);
  const { data: history } = useInvestigationHistory(tab === "history" ? ref : undefined);

  if (isLoading) return <PageShell title="Investigation"><Skeleton height={400} /></PageShell>;
  if (!data) {
    return (
      <PageShell title="Investigation">
        <EmptyState icon={ScrollText} title="Not found" description="No investigation with that reference." />
      </PageShell>
    );
  }

  const liveEntities = data.entities.filter((e) => !e.removed_at);
  const removedEntities = data.entities.filter((e) => e.removed_at);
  const liveAlerts = data.alerts.filter((a) => !a.detached_at);

  return (
    <PageShell title={data.title} subtitle={`${data.inv_ref} · opened by ${data.opened_by}`}>
      <Card className={styles.headCard}>
        <div className={styles.headRow}>
          <Badge tone={data.state === "closed" ? "neutral" : "accent"}>
            {describeState(data.state, data.outcome)}
          </Badge>
          <span className={styles.confidence}>
            confidence <strong>{data.confidence}</strong>
          </span>
          <span className={styles.assigned}>
            {data.assigned_to ? `assigned to ${data.assigned_to}` : "unassigned"}
          </span>
        </div>

        <h2 className={styles.sectionLabel}>Hypothesis</h2>
        <p className={styles.body}>{data.hypothesis}</p>
        {/* The basis travels with the level. A confidence with no stated
            reasoning is a word standing in for an argument. */}
        <p className={styles.basis}>
          <strong>Why {data.confidence}:</strong> {data.confidence_basis}
        </p>

        {data.outcome ? (
          <div className={styles.outcomeBlock}>
            <h2 className={styles.sectionLabel}>
              <CheckCircle2 size={14} aria-hidden /> Outcome — {data.outcome}
            </h2>
            <p className={styles.body}>{data.outcome_rationale}</p>
            <p className={styles.closedBy}>
              Closed by {data.closed_by} · {when(data.closed_at)}
            </p>
          </div>
        ) : null}

        {data.reviews.length > 0 ? (
          <div className={styles.reviews}>
            <h2 className={styles.sectionLabel}>
              <Gavel size={14} aria-hidden /> Review
            </h2>
            {data.reviews.map((r) => (
              <div
                key={r.review_id}
                className={r.concurs ? styles.review : styles.reviewDissent}
              >
                <span className={styles.reviewWho}>
                  {r.concurs ? <UserCheck size={13} aria-hidden /> : <ShieldAlert size={13} aria-hidden />}
                  {r.reviewer} ({r.reviewer_role}) {r.concurs ? "concurs with" : "does not concur with"}{" "}
                  {r.outcome_reviewed}
                </span>
                {r.note ? <p className={styles.reviewNote}>{r.note}</p> : null}
                <span className={styles.reviewWhen}>{when(r.reviewed_at)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <SegmentedControl
        segments={[
          { value: "work" as const, label: "Findings", count: data.findings.length },
          { value: "evidence" as const, label: "Evidence", count: liveAlerts.length + liveEntities.length },
          { value: "history" as const, label: "History" },
        ]}
        value={tab}
        onChange={setTab}
        ariaLabel="Investigation section"
        className={styles.tabs}
      />

      {tab === "work" ? (
        <>
          {data.findings.length === 0 ? (
            <EmptyState icon={ScrollText} title="No findings recorded" description="Nothing has been concluded in this investigation yet." />
          ) : (
            <div className={styles.list}>
              {data.findings.map((f) => {
                const standing = findingStanding(f);
                return (
                  <Card key={f.finding_id} className={standing === "standing" ? styles.finding : styles.findingRetired}>
                    <p className={styles.body}>{f.statement}</p>
                    <div className={styles.meta}>
                      <span>confidence {f.confidence}</span>
                      <span>
                        {f.author_username} ({f.author_role})
                      </span>
                      <span>{when(f.recorded_at)}</span>
                      {standing !== "standing" ? <Badge tone="neutral">{standing}</Badge> : null}
                    </div>
                    <div className={styles.cites}>
                      cites: {f.cites.join(", ")}
                    </div>
                    {f.withdrawal_reason ? (
                      <p className={styles.withdrawn}>Withdrawn by {f.withdrawn_by}: {f.withdrawal_reason}</p>
                    ) : null}
                  </Card>
                );
              })}
            </div>
          )}

          {data.analyst_assessments.length > 0 ? (
            <Card className={styles.dissentCard}>
              <h2 className={styles.sectionLabel}>
                <AlertTriangle size={14} aria-hidden /> Analyst assessments recorded here
              </h2>
              {data.analyst_assessments.map((a) => (
                <div key={a.analyst_assessment_id} className={styles.dissentRow}>
                  <span className={styles.subject}>{a.subject_ref}</span>
                  {/* Both bands, always. Showing only the analyst's would hide
                      that there is a disagreement at all. */}
                  <span>
                    ARGUS: <strong>{a.machine_band ?? "not assessed"}</strong> · analyst:{" "}
                    <strong>{a.analyst_band}</strong>
                    {a.dissents === true ? <Badge tone="high">disagrees</Badge> : null}
                  </span>
                  <p className={styles.body}>{a.rationale}</p>
                  <span className={styles.reviewWhen}>
                    {a.author_username} ({a.author_role}) · {when(a.recorded_at)}
                  </span>
                </div>
              ))}
            </Card>
          ) : null}
        </>
      ) : null}

      {tab === "evidence" ? (
        <div className={styles.list}>
          {liveAlerts.map((a) => (
            <Card key={a.alert_key} className={styles.evidence}>
              <div className={styles.evidenceHead}>
                <Link2 size={14} aria-hidden />
                <span className={styles.title}>{a.title}</span>
                <Badge tone="neutral">{a.rule_id} v{a.rule_version}</Badge>
              </div>
              <div className={styles.meta}>
                <span>attached by {a.attached_by}</span>
                <span>{when(a.attached_at)}</span>
                {a.attach_reason ? <span>{a.attach_reason}</span> : null}
              </div>
            </Card>
          ))}
          {liveEntities.map((e) => (
            <Card key={e.link_id} className={styles.evidence}>
              <div className={styles.evidenceHead}>
                <span className={styles.subject}>{e.entity_ref}</span>
                <Badge tone="neutral">{e.entity_type}</Badge>
              </div>
              <p className={styles.body}>{e.reason}</p>
              <div className={styles.meta}>
                <span>linked by {e.linked_by}</span>
                <span>{when(e.linked_at)}</span>
              </div>
            </Card>
          ))}
          {removedEntities.length > 0 ? (
            <Card className={styles.removedCard}>
              <h2 className={styles.sectionLabel}>Evidence that was removed</h2>
              {/* Kept visible. That a piece of evidence was once linked, and who
                  unlinked it and why, is itself part of the record. */}
              {removedEntities.map((e) => (
                <div key={e.link_id} className={styles.removedRow}>
                  <span className={styles.subject}>{e.entity_ref}</span>
                  <span>removed by {e.removed_by}: {e.removal_reason}</span>
                  <span className={styles.reviewWhen}>{when(e.removed_at)}</span>
                </div>
              ))}
            </Card>
          ) : null}
          {liveAlerts.length === 0 && liveEntities.length === 0 && removedEntities.length === 0 ? (
            <EmptyState icon={Link2} title="No evidence linked" description="Nothing has been attached to this investigation." />
          ) : null}
        </div>
      ) : null}

      {tab === "history" ? (
        history ? (
          <>
            <Card className={history.integrity.consistent ? styles.integrityOk : styles.integrityBroken}>
              {history.integrity.consistent ? (
                <span className={styles.integrityLine}>
                  <CheckCircle2 size={14} aria-hidden />
                  Every recorded change accounts for the one before it.
                </span>
              ) : (
                <span className={styles.integrityLine}>
                  <ShieldAlert size={14} aria-hidden />
                  {history.integrity.break?.describes}
                </span>
              )}
            </Card>
            <div className={styles.timeline}>
              {history.events.map((e) => (
                <div key={e.event_id} className={styles.event}>
                  <Clock size={12} aria-hidden />
                  <span className={styles.eventWhen}>{when(e.occurred_at)}</span>
                  <span className={styles.eventActor}>{e.actor_username}</span>
                  <span className={styles.eventBody}>
                    {e.field ? (
                      <>
                        <strong>{e.field}</strong>: {JSON.stringify(e.old_value)} →{" "}
                        {JSON.stringify(e.new_value)}
                      </>
                    ) : (
                      <>
                        {e.event_type.replace(/_/g, " ")}
                        {e.note ? ` — ${e.note}` : ""}
                      </>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Skeleton height={240} />
        )
      ) : null}
    </PageShell>
  );
}
