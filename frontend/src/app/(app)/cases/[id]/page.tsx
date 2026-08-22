"use client";

import { Info, ShieldHalf, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { useCase } from "@/hooks/useCases";
import { useCaseSummary } from "@/hooks/useAssistant";
import { useAlerts } from "@/hooks/useAlerts";
import { CaseFootprint } from "@/components/cases/CaseFootprint";
import {
  CASE_PRIORITY_TONE,
  CASE_STATUS_LABEL,
  CASE_STATUS_TONE,
} from "@/lib/caseLabels";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import styles from "./page.module.css";

export default function CaseWorkspacePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;

  const { data: caseDetail, isLoading } = useCase(caseId);
  const summary = useCaseSummary();
  // One request for the whole alert set; related alerts are matched locally by
  // intersecting involved_entity_ids with the evidence board.
  const { data: alertsPage } = useAlerts();

  if (isLoading) {
    return (
      <PageShell>
        <Skeleton height={80} />
      </PageShell>
    );
  }

  if (!caseDetail) {
    return (
      <PageShell title="Case Workspace" subtitle={caseId}>
        <EmptyState icon={ShieldHalf} title="Case not found" description={`No case with ID ${caseId}.`} />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.subtitle}>{caseDetail.case_id}</span>
          <span className={styles.title}>{caseDetail.title}</span>
          <div className={styles.badgeRow}>
            <Badge tone={CASE_STATUS_TONE[caseDetail.status]}>{CASE_STATUS_LABEL[caseDetail.status]}</Badge>
            <Badge tone={CASE_PRIORITY_TONE[caseDetail.priority]}>{caseDetail.priority}</Badge>
          </div>
        </div>
      </div>

      {/* Read-only, and said so where it is read rather than only in a commit
          message. This record was written by a source; the status and priority
          on it are that source's, not a judgement anyone here made. */}
      <div className={styles.provenanceNote}>
        <Info size={15} aria-hidden />
        <span>
          Reported by a source and shown as reported. Nothing on this page was
          concluded by an analyst in this deployment, and it cannot be edited here.
          To record your own judgement about these entities, open an{" "}
          <Link href="/investigations">investigation</Link>.
        </span>
      </div>

      <div className={styles.layout}>
        <div className={styles.column}>
          <Card>
            <CaseFootprint
              entities={caseDetail.linked_entities ?? []}
              alerts={alertsPage?.data}
              caseId={caseDetail.case_id}
            />
          </Card>

          <Card>
            <div className={styles.panelTitle}>Notes as reported</div>
            <p className={styles.reportedNotes}>{caseDetail.notes || "No notes on this record."}</p>
          </Card>

          <Card>
            <div className={styles.panelTitle}>Summary</div>
            {summary.data ? (
              <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text-secondary)" }}>{summary.data.summary}</p>
            ) : (
              <EmptyState
                icon={Sparkles}
                title="No summary generated yet"
                description="A deterministic template composer turns this case's status, priority, evidence board, and notes into analyst-brief prose — no LLM involved."
                actions={
                  <Button size="sm" onClick={() => summary.mutate(caseDetail.case_id)} disabled={summary.isPending}>
                    {summary.isPending ? <Spinner size={16} /> : "Generate Summary"}
                  </Button>
                }
              />
            )}
          </Card>
        </div>

        <div className={styles.column}>
          <Card>
            <div className={styles.panelTitle}>Evidence Board</div>
            {caseDetail.linked_entities.length === 0 ? (
              <p style={{ fontSize: 13, color: "var(--text-tertiary)" }}>No entities linked yet.</p>
            ) : (
              caseDetail.linked_entities.map((entity, i) => {
                const id = entityId(entity.label, entity.properties);
                const name = entityName(entity.label, entity.properties);
                return (
                  <div key={i} className={styles.evidenceRow}>
                    <div>
                      {id ? (
                        <Link href={`/entities/${id}`} className={styles.evidenceLink}>
                          {name}
                        </Link>
                      ) : (
                        <span className={styles.evidenceLink}>{name}</span>
                      )}
                      <div className={styles.evidenceLabel}>{entity.label}</div>
                    </div>
                  </div>
                );
              })
            )}
          </Card>

          <Card>
            <div className={styles.panelTitle}>Details</div>
            <div className={styles.evidenceRow}>
              <span className={styles.evidenceLabel}>Assigned Analyst</span>
              <span>{caseDetail.assigned_analyst}</span>
            </div>
            <div className={styles.evidenceRow}>
              <span className={styles.evidenceLabel}>Opened</span>
              <span>{formatRelativeTime(caseDetail.opened_at)}</span>
            </div>
            {caseDetail.closed_at && (
              <div className={styles.evidenceRow}>
                <span className={styles.evidenceLabel}>Closed</span>
                <span>{formatRelativeTime(caseDetail.closed_at)}</span>
              </div>
            )}
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
