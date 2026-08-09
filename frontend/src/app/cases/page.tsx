"use client";

import { Plus, ShieldHalf } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { useCases, useCreateCase } from "@/hooks/useCases";
import { formatRelativeTime } from "@/lib/formatters";
import type { CaseSummary } from "@/lib/types";
import styles from "./page.module.css";

const STATUS_TABS = ["All", "Draft", "Open", "UnderReview", "Closed"];

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

export default function CasesPage() {
  return (
    <Suspense fallback={<PageShell title="Cases" subtitle="Manage ongoing investigations">{null}</PageShell>}>
      <CasesPageInner />
    </Suspense>
  );
}

function CasesPageInner() {
  const searchParams = useSearchParams();
  const [statusTab, setStatusTab] = useState(() => searchParams.get("status") ?? "All");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [notes, setNotes] = useState("");

  const { data, isLoading } = useCases(statusTab === "All" ? undefined : statusTab);
  const createCase = useCreateCase();
  const { showToast } = useToast();

  const cases = data?.data ?? [];

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

  return (
    <PageShell
      title="Cases"
      subtitle="Manage ongoing investigations"
      actions={
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus size={16} /> New Case
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
              {createCase.isPending ? "Creating…" : "Create Case"}
            </Button>
          </div>
        </div>
      )}

      <div style={{ marginBottom: "var(--space-5)" }}>
        <Tabs tabs={STATUS_TABS} active={statusTab} onChange={setStatusTab} />
      </div>

      {isLoading ? (
        <div className={styles.grid}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height={110} />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <EmptyState icon={ShieldHalf} title="No cases" description="No investigations match this filter." />
      ) : (
        <div className={styles.grid}>
          {cases.map((c) => (
            <Link key={c.case_id} href={`/cases/${c.case_id}`} className={styles.caseCard}>
              <div className={styles.caseTopRow}>
                <span className={styles.caseTitle}>{c.title}</span>
              </div>
              <div className={styles.badgeRow}>
                <Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge>
                <Badge tone={PRIORITY_TONE[c.priority]}>{c.priority}</Badge>
              </div>
              <span className={styles.caseMeta}>
                {c.case_id} · Opened {formatRelativeTime(c.opened_at)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </PageShell>
  );
}
