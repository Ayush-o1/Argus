"use client";

import { Download, FileCheck2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { CLASSIFICATION_TONE } from "@/lib/calibration";
import { formatTimestamp } from "@/lib/provenance";
import { nextFixtureExports, nextFixtureInvestigations } from "@/lib/next/fixtures";
import styles from "./CustodyRegister.module.css";

/**
 * Report mode: findings and custody, built on the real export shape
 * (`ExportRecord` — required immutable purpose, content_sha256, retention/
 * disposal) rather than a generic "download" list.
 *
 * "Produce an export" and "Verify" are shown, not wired: both are real
 * writes on the live page (`ExportPanel` in
 * `app/(app)/investigations/[ref]/page.tsx`) — one inserts a BYTEA row,
 * the other re-hashes stored content and logs the check as an access event.
 * Fixture investigations have no row in Postgres to write against, and a
 * button that fakes success would be exactly the invented successful state
 * this rebuild rules out. Disabled with the reason stated, matching the
 * deferral pattern already used in the Graph lens (`onExpandNode`) and
 * Evidence mode (`EvidenceLedger`) — this becomes live in the same Phase 12
 * pass that replaces every other fixture adapter.
 */
export function CustodyRegister() {
  const investigationTitle = new Map(nextFixtureInvestigations.map((inv) => [inv.investigation_id, inv]));

  return (
    <div className={styles.wrap}>
      <Card className={styles.formCard}>
        <h2 className={styles.sectionLabel}>Produce an export</h2>
        <p className={styles.basis}>
          A stated purpose is required and recorded against the artifact permanently. Not wired to a live write in this build — see
          the module note.
        </p>
        <div className={styles.form}>
          <input className={styles.input} placeholder="Why is this being exported?" disabled />
          <select className={styles.select} disabled aria-label="Export format">
            <option>HTML — for a person</option>
            <option>Markdown — for a document or a diff</option>
            <option>PDF — for printing or emailing</option>
            <option>JSON — for a machine</option>
          </select>
          <Button size="sm" disabled>
            Export
          </Button>
        </div>
      </Card>

      {nextFixtureExports.length === 0 ? (
        <EmptyState icon={Download} title="Nothing has been exported" description="No copy of any investigation has left the system." />
      ) : (
        <div className={styles.list}>
          {nextFixtureExports.map((e) => {
            const inv = e.investigation_id ? investigationTitle.get(e.investigation_id) : null;
            return (
              <Card key={e.export_id} className={styles.record}>
                <div className={styles.recordHead}>
                  <Badge tone={CLASSIFICATION_TONE[e.classification]}>{e.classification.toUpperCase()}</Badge>
                  <span className={styles.format}>{e.format.toUpperCase()}</span>
                  <span className={styles.meta}>{e.byte_size.toLocaleString("en-US")} bytes</span>
                  {e.disposed_at ? <Badge tone="neutral">disposed</Badge> : null}
                </div>
                {inv ? <p className={styles.title}>{inv.title}</p> : null}
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
                  <Button size="sm" variant="secondary" disabled title="Not wired to a live write in this build.">
                    <Download size={13} aria-hidden /> Download
                  </Button>
                  <Button size="sm" variant="secondary" disabled title="Not wired to a live write in this build.">
                    <FileCheck2 size={13} aria-hidden /> Verify
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
