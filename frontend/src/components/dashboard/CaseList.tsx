"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { CASE_STATUS_LABEL, CASE_STATUS_TONE } from "@/lib/caseLabels";
import { formatRelativeTime } from "@/lib/formatters";
import type { CaseSummary } from "@/lib/types";
import { ShieldHalf } from "lucide-react";
import styles from "./CaseList.module.css";

export function CaseList({ cases }: { cases: CaseSummary[] }) {
  // The panel is titled "Active cases", so closed ones don't belong in it —
  // the dashboard endpoint returns the most recent cases regardless of state.
  const active = cases.filter((c) => c.status !== "Closed");

  if (active.length === 0) {
    return <EmptyState icon={ShieldHalf} title="No active cases" description="No investigations are currently open." />;
  }

  return (
    <div className={styles.list}>
      {active.map((c) => (
        <Link key={c.case_id} href={`/cases/${c.case_id}`} className={styles.row}>
          <div className={styles.body}>
            <span className={styles.title}>{c.title}</span>
            <span className={styles.meta}>
              {c.case_id} · {formatRelativeTime(c.opened_at)}
            </span>
          </div>
          <Badge tone={CASE_STATUS_TONE[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge>
        </Link>
      ))}
    </div>
  );
}
