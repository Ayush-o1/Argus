"use client";

import { Plus, ShieldHalf } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { SegmentedControl, type Segment } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, type TableColumn } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { useCases, useCreateCase } from "@/hooks/useCases";
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
    <Suspense fallback={<PageShell title="Cases" subtitle="Investigation workspaces">{null}</PageShell>}>
      <CasesPageInner />
    </Suspense>
  );
}

function CasesPageInner() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<StatusFilter>(() => (searchParams.get("status") as StatusFilter) ?? "All");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [notes, setNotes] = useState("");

  const { data, isLoading } = useCases(status === "All" ? undefined : status);
  const createCase = useCreateCase();
  const { showToast } = useToast();

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

  function handleCreate() {
    if (!title.trim()) return;
    createCase.mutate(
      { title: title.trim(), priority, notes },
      {
        onSuccess: (created) => {
          setTitle("");
          setNotes("");
          setPriority("Medium");
          setShowForm(false);
          showToast(`Case ${created.case_id} created`, "success");
        },
        onError: () => {
          showToast("Failed to create case — please try again", "error");
        },
      },
    );
  }

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
      title="Cases"
      subtitle="Investigation workspaces — live cases first, most urgent at the top"
      actions={
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus size={16} /> New case
        </Button>
      }
    >
      {showForm && (
        <div className={styles.createForm}>
          <Input placeholder="Case title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          <div className={styles.formRow}>
            <Select value={priority} onChange={(e) => setPriority(e.target.value)}>
              {["Low", "Medium", "High", "Critical"].map((p) => (
                <option key={p} value={p}>
                  {p} priority
                </option>
              ))}
            </Select>
          </div>
          <Textarea placeholder="Initial notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className={styles.formActions}>
            <Button variant="secondary" size="sm" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleCreate} disabled={!title.trim() || createCase.isPending}>
              {createCase.isPending ? "Creating…" : "Create case"}
            </Button>
          </div>
        </div>
      )}

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
