"use client";

import { ShieldHalf, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Spinner } from "@/components/ui/Spinner";
import { useAddCaseEntity, useCase, useRemoveCaseEntity, useUpdateCase } from "@/hooks/useCases";
import { useCaseSummary } from "@/hooks/useAssistant";
import { entityId, entityName } from "@/lib/entityDisplay";
import { formatRelativeTime } from "@/lib/formatters";
import type { CaseSummary } from "@/lib/types";
import styles from "./page.module.css";

const STATUS_TONE: Record<CaseSummary["status"], "neutral" | "accent" | "high" | "low"> = {
  Draft: "neutral",
  Open: "accent",
  UnderReview: "high",
  Closed: "low",
};

const PRIORITY_TONE: Record<CaseSummary["priority"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

export default function CaseWorkspacePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;

  const { data: caseDetail, isLoading } = useCase(caseId);
  const updateCase = useUpdateCase(caseId);
  const addEntity = useAddCaseEntity(caseId);
  const removeEntity = useRemoveCaseEntity(caseId);
  const summary = useCaseSummary();

  const [newEntityId, setNewEntityId] = useState("");

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

  function handleAddEntity() {
    if (!newEntityId.trim()) return;
    addEntity.mutate({ entity_id: newEntityId.trim() }, { onSuccess: () => setNewEntityId("") });
  }

  return (
    <PageShell>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.subtitle}>{caseDetail.case_id}</span>
          <span className={styles.title}>{caseDetail.title}</span>
          <div className={styles.badgeRow}>
            <Badge tone={STATUS_TONE[caseDetail.status]}>{caseDetail.status}</Badge>
            <Badge tone={PRIORITY_TONE[caseDetail.priority]}>{caseDetail.priority}</Badge>
          </div>
        </div>
        <div className={styles.controlsRow}>
          <select
            className={styles.select}
            value={caseDetail.status}
            onChange={(e) => updateCase.mutate({ status: e.target.value })}
          >
            {["Draft", "Open", "UnderReview", "Closed"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className={styles.select}
            value={caseDetail.priority}
            onChange={(e) => updateCase.mutate({ priority: e.target.value })}
          >
            {["Low", "Medium", "High", "Critical"].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={styles.layout}>
        <div className={styles.column}>
          <NotesPanel
            key={caseDetail.case_id}
            initialNotes={caseDetail.notes}
            onSave={(notes) => updateCase.mutate({ notes })}
            saving={updateCase.isPending}
          />

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
                    {id && (
                      <button
                        type="button"
                        className={styles.removeButton}
                        onClick={() => removeEntity.mutate(id)}
                        aria-label={`Remove ${name}`}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                );
              })
            )}
            <div className={styles.addEntityRow}>
              <input
                className={styles.input}
                placeholder="Entity ID, e.g. PRS-0002858"
                value={newEntityId}
                onChange={(e) => setNewEntityId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddEntity()}
              />
              <Button size="sm" onClick={handleAddEntity} disabled={!newEntityId.trim() || addEntity.isPending}>
                Add
              </Button>
            </div>
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

function NotesPanel({
  initialNotes,
  onSave,
  saving,
}: {
  initialNotes: string;
  onSave: (notes: string) => void;
  saving: boolean;
}) {
  const [notes, setNotes] = useState(initialNotes);
  const dirty = notes !== initialNotes;

  return (
    <Card>
      <div className={styles.panelTitle}>Notes</div>
      <textarea
        className={styles.notesTextarea}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Investigation notes…"
      />
      <div className={styles.notesActions}>
        <Button size="sm" disabled={!dirty || saving} onClick={() => onSave(notes)}>
          {saving ? "Saving…" : "Save Notes"}
        </Button>
      </div>
    </Card>
  );
}
