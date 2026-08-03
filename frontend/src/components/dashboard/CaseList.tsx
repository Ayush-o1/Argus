"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatRelativeTime } from "@/lib/formatters";
import type { CaseSummary } from "@/lib/types";
import { ShieldHalf } from "lucide-react";
import styles from "./CaseList.module.css";

const STATUS_TONE: Record<CaseSummary["status"], "neutral" | "accent" | "low" | "high"> = {
  Draft: "neutral",
  Open: "accent",
  UnderReview: "high",
  Closed: "low",
};

export function CaseList({ cases }: { cases: CaseSummary[] }) {
  if (cases.length === 0) {
    return <EmptyState icon={ShieldHalf} title="No cases" description="No investigations opened yet." />;
  }

  return (
    <div className={styles.list}>
      {cases.map((c) => (
        <Link key={c.case_id} href={`/cases/${c.case_id}`} className={styles.row}>
          <div className={styles.body}>
            <span className={styles.title}>{c.title}</span>
            <span className={styles.meta}>
              {c.case_id} · {formatRelativeTime(c.opened_at)}
            </span>
          </div>
          <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge>
        </Link>
      ))}
    </div>
  );
}
