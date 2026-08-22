"use client";

import { Info, ShieldHalf } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl, type Segment } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, type TableColumn } from "@/components/ui/Table";
import { useCases } from "@/hooks/useCases";
import { formatDate, formatRelativeTime } from "@/lib/formatters";
import { CASE_STATUS_LABEL, CASE_STATUS_TONE } from "@/lib/caseLabels";
import type { CaseSummary } from "@/lib/types";
import styles from "./page.module.css";

type StatusFilter = "All" | "Draft" | "Open" | "UnderReview" | "Closed";

const PRIORITY_TONE: Record<CaseSummary["priority"], "critical" | "high" | "medium" | "low"> = {
  Critical: "critical",
  High: "high",
  Medium: "medium",
  Low: "low",
};

const PRIORITY_RANK: Record<CaseSummary["priority"], number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
};

/** Closed work should never outrank live work in a queue, regardless of how
 * urgent it was when it was open. */
const STATUS_RANK: Record<CaseSummary["status"], number> = {
  UnderReview: 0,
  Open: 1,
  Draft: 2,
  Closed: 3,
};

export default function CasesPage() {
  return (
    <Suspense fallback={<PageShell title="Source case records" subtitle="Case records reported by a source">{null}</PageShell>}>
      <CasesPageInner />
    </Suspense>
  );
}

function CasesPageInner() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<StatusFilter>(() => (searchParams.get("status") as StatusFilter) ?? "All");
  const { data, isLoading } = useCases(status === "All" ? undefined : status);

  // Ordered the way an analyst picks up work: live cases first, most urgent
  // within that, newest as the tiebreak. The API returns creation order only.
  const cases = useMemo(
    () =>
      [...(data?.data ?? [])].sort(
        (a, b) =>
          STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
          PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
          new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime(),
      ),
    [data],
  );

  const counts = useMemo(() => {
    const all = data?.data ?? [];
    return {
      open: all.filter((c) => c.status === "Open").length,
      review: all.filter((c) => c.status === "UnderReview").length,
    };
  }, [data]);


  const statusSegments: Segment<StatusFilter>[] = [
    { value: "All", label: "All" },
    { value: "Open", label: "Open", count: status === "All" ? counts.open : undefined },
    { value: "UnderReview", label: CASE_STATUS_LABEL.UnderReview, count: status === "All" ? counts.review : undefined },
    { value: "Draft", label: "Draft" },
    { value: "Closed", label: "Closed" },
  ];

  const columns: TableColumn<CaseSummary>[] = [
    {
      key: "title",
      header: "Case",
      render: (c) => (
        <div className={styles.titleCell}>
          <span className={styles.caseTitle}>{c.title}</span>
          <span className={styles.caseId}>{c.case_id}</span>
        </div>
      ),
    },
    {
      key: "priority",
      header: "Priority",
      render: (c) => <Badge tone={PRIORITY_TONE[c.priority]}>{c.priority}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      render: (c) => <Badge tone={CASE_STATUS_TONE[c.status]}>{CASE_STATUS_LABEL[c.status]}</Badge>,
    },
    {
      key: "opened",
      header: "Opened",
      align: "right",
      render: (c) => (
        <span className={styles.ageCell} title={formatDate(c.opened_at)}>
          {formatRelativeTime(c.opened_at)}
        </span>
      ),
    },
  ];

  return (
    <PageShell
      title="Source case records"
      subtitle="Case records reported by a source — not this deployment's own investigations"
    >
      {/* Every case in this store was written by the scenario generator from a
          storyline it had just planted: titled after the storyline, linked to
          exactly the entities it named, and assigned to one of five invented
          analyst names. Reading them is fine. Presenting them as analyst work
          was the defect — the same one Phase 7 removed from the alert queue,
          in the surface where it does the most damage, because a fabricated
          human judgement is one a reader has no way to discount. */}
      <div className={styles.provenanceNote}>
        <Info size={15} aria-hidden />
        <span>
          These records come from a registered source and are shown as reported. They
          are not investigations opened in this deployment, and nothing here has been
          concluded by an analyst. Work opened by analysts — with a hypothesis,
          evidence, findings and an outcome — lives under{" "}
          <Link href="/investigations">Investigations</Link>.
        </span>
      </div>


      <div className={styles.filterRow}>
        <SegmentedControl segments={statusSegments} value={status} onChange={setStatus} ariaLabel="Filter cases by status" />
        <span className={styles.resultCount}>
          {cases.length} {cases.length === 1 ? "case" : "cases"}
        </span>
      </div>

      {isLoading ? (
        <div className={styles.skeletons}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} height={44} />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <EmptyState
          icon={ShieldHalf}
          title="No cases"
          description="No investigations match this filter. Create a case to start tracking evidence and entities."
        />
      ) : (
        <Table
          columns={columns}
          rows={cases}
          getRowKey={(c) => c.case_id}
          getRowHref={(c) => `/cases/${c.case_id}`}
        />
      )}
    </PageShell>
  );
}
