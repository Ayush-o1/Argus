"use client";

import { FileSearch, Gavel, ShieldQuestion, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  useInvestigationVocabulary,
  useInvestigations,
  useOutcomesByRule,
} from "@/hooks/useInvestigations";
import { describeState, type InvestigationState } from "@/lib/investigations";
import styles from "./page.module.css";

type Filter = InvestigationState | "";

/**
 * Investigations — what a person concluded about what ARGUS found.
 *
 * This is a different object from the `/cases` list, and the difference is the
 * point. Every `Case` in the graph was written by the scenario generator from a
 * storyline it had just planted, down to an invented analyst name; presenting
 * those as investigations would dress the answer key as human judgement. They
 * are still readable, on their own page, labelled as what they are.
 *
 * Nothing here is seeded. An empty queue means nobody has opened one yet, and
 * that is the honest thing for it to say.
 */
export default function InvestigationsPage() {
  const [filter, setFilter] = useState<Filter>("");
  const { data, isLoading } = useInvestigations(filter);
  const { data: vocabulary } = useInvestigationVocabulary();
  const { data: outcomes } = useOutcomesByRule();

  const rows = data?.data ?? [];
  // From `meta`, never from `rows.length`. The page is 100 rows and the table
  // may be longer, and a heading that counts the page is the defect the audit
  // found on four separate surfaces.
  const total = data?.meta?.total ?? 0;

  return (
    <PageShell
      title="Investigations"
      subtitle="Analyst judgement about ARGUS's findings — with the outcome that makes detection measurable."
    >
      <SegmentedControl
        segments={[
          { value: "" as const, label: "All", count: total },
          { value: "open" as const, label: "Not started" },
          { value: "active" as const, label: "Being worked" },
          { value: "closed" as const, label: "Concluded" },
        ]}
        value={filter}
        onChange={setFilter}
        ariaLabel="Investigation state"
        className={styles.tabs}
      />

      {outcomes && outcomes.closed_total > 0 ? (
        <Card className={styles.outcomeCard}>
          <div className={styles.outcomeRow}>
            {Object.entries(outcomes.by_outcome).map(([code, n]) => (
              <span key={code} className={styles.outcomeChip}>
                <strong>{n}</strong> {code}
              </span>
            ))}
          </div>
          {/* The denominator travels with the figures, and no rate is shown.
              A precision over four outcomes has as many digits as one over
              four thousand. */}
          <p className={styles.basisNote}>{outcomes.basis_note}</p>
        </Card>
      ) : null}

      {isLoading ? (
        <Skeleton height={280} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title={filter ? "Nothing in this state" : "No investigations yet"}
          description={
            filter
              ? "No investigation is currently in this state."
              : "Investigations are opened from the alert queue. Nothing here is pre-populated — the case records the generator wrote live on their own page, marked as source-reported."
          }
        />
      ) : (
        <div className={styles.list}>
          {rows.map((row) => (
            <Link
              key={row.investigation_id}
              href={`/investigations/${encodeURIComponent(row.inv_ref)}`}
              className={styles.row}
            >
              <div className={styles.rowMain}>
                <div className={styles.rowHead}>
                  <span className={styles.ref}>{row.inv_ref}</span>
                  <span className={styles.title}>{row.title}</span>
                </div>
                <div className={styles.meta}>
                  <Badge tone={row.state === "closed" ? "neutral" : "accent"}>
                    {describeState(row.state, row.outcome)}
                  </Badge>
                  <span>confidence {row.confidence}</span>
                  <span>
                    {row.alert_count} alert{row.alert_count === 1 ? "" : "s"}
                  </span>
                  <span>
                    {row.finding_count} finding{row.finding_count === 1 ? "" : "s"}
                  </span>
                  {row.open_action_count > 0 ? (
                    <span>{row.open_action_count} action outstanding</span>
                  ) : null}
                  <span className={styles.who}>
                    {row.assigned_to ? `assigned to ${row.assigned_to}` : "unassigned"}
                  </span>
                </div>
              </div>
              {/* A dissenting review is the single most informative thing on
                  this row, so it is the one thing shown on the right. */}
              {row.dissenting_reviews > 0 ? (
                <span className={styles.dissent}>
                  <TriangleAlert size={14} aria-hidden />
                  reviewer disagrees
                </span>
              ) : row.review_count > 0 ? (
                <span className={styles.reviewed}>
                  <Gavel size={14} aria-hidden />
                  reviewed
                </span>
              ) : null}
            </Link>
          ))}
        </div>
      )}

      {vocabulary ? (
        <Card className={styles.vocabCard}>
          <h2 className={styles.vocabTitle}>
            <ShieldQuestion size={16} aria-hidden /> What the outcomes mean
          </h2>
          <dl className={styles.vocab}>
            {vocabulary.outcomes.map((o) => (
              <div key={o.code} className={styles.vocabItem}>
                <dt>
                  {o.label}
                  <span className={styles.counts}>
                    {o.counts_as_correct === null
                      ? "excluded from precision"
                      : o.counts_as_correct
                        ? "counts for the rule"
                        : "counts against the rule"}
                  </span>
                </dt>
                <dd>{o.means}</dd>
              </div>
            ))}
          </dl>
          <p className={styles.basisNote}>{vocabulary.outcome_note}</p>
        </Card>
      ) : null}
    </PageShell>
  );
}
