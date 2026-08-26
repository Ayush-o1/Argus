"use client";

import { useState } from "react";
import { Download, FileCheck2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useHasPermission } from "@/hooks/useAuth";
import { useCreateExport, useExports, useVerifyExport } from "@/hooks/useCalibration";
import { useInvestigations } from "@/hooks/useInvestigations";
import { API_BASE_URL } from "@/lib/api";
import { CLASSIFICATION_TONE, type ExportFormat } from "@/lib/calibration";
import { formatTimestamp } from "@/lib/provenance";
import styles from "./CustodyRegister.module.css";

/**
 * Report mode: findings and custody, built on the real export shape
 * (`ExportRecord` — required immutable purpose, content_sha256, retention/
 * disposal) rather than a generic "download" list.
 *
 * Live-wired (Phase 12): `useExports()` unscoped (no `investigation_id`)
 * lists every export across every investigation, since this register isn't
 * nested under one investigation's page the way the live `ExportPanel` is —
 * an investigation picker below chooses which one "Produce an export"
 * targets. `useCreateExport`/`useVerifyExport` are the exact mutations that
 * component uses; Download links straight at the backend's own origin for
 * the same cross-origin reason its own comment gives. All three are real
 * writes/reads against real Postgres rows now that this register isn't
 * fixture-scoped — nothing here fakes a result the backend didn't actually
 * return.
 *
 * Found live, not assumed: `export:read` (list/verify/download) and
 * `export:create` are separate permissions — an analyst holds the former
 * but not the latter (confirmed against the real backend: a create attempt
 * 403s with "Role 'analyst' lacks permission 'export:create'"). Producing
 * an export moves data outside the system, so it is gated more narrowly
 * than reading the register — the form below checks for it explicitly
 * rather than rendering a button that would 403 for most roles that can
 * otherwise use this page.
 */
export function CustodyRegister() {
  const [purpose, setPurpose] = useState("");
  const [format, setFormat] = useState<ExportFormat>("html");
  const [targetRef, setTargetRef] = useState<string | null>(null);

  const canCreateExport = useHasPermission("export:create");
  const { data: investigationsEnvelope, isLoading: investigationsLoading } = useInvestigations();
  const { data: exportsEnvelope, isLoading: exportsLoading, refetch } = useExports();
  const create = useCreateExport();
  const verify = useVerifyExport();

  const investigations = investigationsEnvelope?.data ?? [];
  const investigationTitle = new Map(investigations.map((inv) => [inv.investigation_id, inv]));
  const investigationRefById = new Map(investigations.map((inv) => [inv.investigation_id, inv.inv_ref]));
  const exports = exportsEnvelope?.data ?? [];
  const selectedRef = targetRef ?? investigations[0]?.inv_ref ?? null;

  return (
    <div className={styles.wrap}>
      <Card className={styles.formCard}>
        <h2 className={styles.sectionLabel}>Produce an export</h2>
        <p className={styles.basis}>A stated purpose is required and recorded against the artifact permanently.</p>
        {!canCreateExport ? (
          <p className={styles.basis}>Your role does not include export:create. You can read and verify the register below.</p>
        ) : investigationsLoading ? (
          <Skeleton height={30} />
        ) : investigations.length === 0 ? (
          <p className={styles.basis}>No investigation exists yet to export from.</p>
        ) : (
          <div className={styles.form}>
            <select
              className={styles.select}
              value={selectedRef ?? ""}
              onChange={(e) => setTargetRef(e.target.value)}
              aria-label="Investigation"
            >
              {investigations.map((inv) => (
                <option key={inv.investigation_id} value={inv.inv_ref}>
                  {inv.inv_ref} — {inv.title}
                </option>
              ))}
            </select>
            <input
              className={styles.input}
              placeholder="Why is this being exported?"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            />
            <select className={styles.select} value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)} aria-label="Export format">
              <option value="html">HTML — for a person</option>
              <option value="markdown">Markdown — for a document or a diff</option>
              <option value="pdf">PDF — for printing or emailing</option>
              <option value="json">JSON — for a machine</option>
            </select>
            <Button
              size="sm"
              disabled={!purpose.trim() || !selectedRef || create.isPending}
              onClick={() =>
                create.mutate(
                  { investigation_ref: selectedRef!, format, purpose: purpose.trim() },
                  { onSuccess: () => { setPurpose(""); void refetch(); } },
                )
              }
            >
              {create.isPending ? "Producing…" : "Export"}
            </Button>
          </div>
        )}
        {create.isError ? <p className={styles.error}>{(create.error as Error).message}</p> : null}
      </Card>

      {exportsLoading ? (
        <Skeleton height={160} />
      ) : exports.length === 0 ? (
        <EmptyState icon={Download} title="Nothing has been exported" description="No copy of any investigation has left the system." />
      ) : (
        <div className={styles.list}>
          {exports.map((e) => {
            const inv = e.investigation_id ? investigationTitle.get(e.investigation_id) : null;
            const invRef = e.investigation_id ? investigationRefById.get(e.investigation_id) : null;
            return (
              <Card key={e.export_id} className={styles.record}>
                <div className={styles.recordHead}>
                  <Badge tone={CLASSIFICATION_TONE[e.classification]}>{e.classification.toUpperCase()}</Badge>
                  <span className={styles.format}>{e.format.toUpperCase()}</span>
                  <span className={styles.meta}>{e.byte_size.toLocaleString("en-US")} bytes</span>
                  {e.disposed_at ? <Badge tone="neutral">disposed</Badge> : null}
                </div>
                {inv ? (
                  <p className={styles.title}>
                    {invRef} — {inv.title}
                  </p>
                ) : null}
                <p className={styles.body}>{e.purpose}</p>
                <div className={styles.meta}>
                  <span>
                    {e.requested_by} ({e.requester_role})
                  </span>
                  <span>{formatTimestamp(e.requested_at)}</span>
                  <span>retained until {formatTimestamp(e.retention_until)}</span>
                </div>
                <div className={styles.hash}>sha256 {e.content_sha256}</div>
                {e.disposed_at ? (
                  <p className={styles.meta}>
                    Disposed {formatTimestamp(e.disposed_at)} by {e.disposed_by} — {e.disposal_reason}
                  </p>
                ) : null}
                <div className={styles.actions}>
                  {!e.disposed_at ? (
                    <a
                      className={styles.downloadLink}
                      href={`${API_BASE_URL}/api/exports/${encodeURIComponent(e.export_id)}/content`}
                    >
                      <Download size={13} aria-hidden /> Download
                    </a>
                  ) : null}
                  <Button size="sm" variant="secondary" onClick={() => verify.mutate(e.export_id)} disabled={verify.isPending}>
                    <FileCheck2 size={13} aria-hidden /> Verify
                  </Button>
                  {verify.data?.export_id === e.export_id ? (
                    <span className={verify.data.intact ? styles.intact : styles.notIntact}>{verify.data.explains}</span>
                  ) : null}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
