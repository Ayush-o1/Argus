"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useMemo } from "react";
import { RISK_COLORS } from "@/lib/theme";
import { formatRelativeTime } from "@/lib/formatters";
import type { GlobalTimeline } from "@/hooks/useTimeline";
import styles from "./NotableMoments.module.css";

/**
 * What actually happened, ranked, inside the current selection.
 *
 * This deliberately covers every flagged record rather than incidents alone.
 * Bursts in this dataset are driven by flagged transactions and
 * communications, so an incidents-only panel went empty exactly when the
 * analyst clicked the most interesting day on the chart — the one moment it
 * most needed to explain.
 */

const SEVERITY_RANK: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3 };

interface Moment {
  id: string;
  kind: "Incident" | "Transaction" | "Communication" | "Event";
  title: string;
  detail: string;
  timestamp: string;
  color: string;
  href: string | null;
  rank: number;
}

function buildMoments(data: GlobalTimeline): Moment[] {
  const moments: Moment[] = [
    ...data.incidents.map((i) => ({
      id: i.id,
      kind: "Incident" as const,
      title: i.subtype,
      detail: i.description,
      timestamp: i.timestamp,
      color: RISK_COLORS[i.severity] ?? "var(--risk-low)",
      href: `/alerts?focus=${i.id}`,
      rank: SEVERITY_RANK[i.severity] ?? 4,
    })),
    ...data.transactions
      .filter((t) => t.flagged)
      .map((t) => ({
        id: t.id,
        kind: "Transaction" as const,
        title: `Flagged ${t.subtype.toLowerCase()} transaction`,
        detail: `₹${t.amount.toLocaleString("en-IN")}`,
        timestamp: t.timestamp,
        color: RISK_COLORS.High,
        href: null,
        rank: 5,
      })),
    ...data.communications
      .filter((c) => c.flagged)
      .map((c) => ({
        id: c.id,
        kind: "Communication" as const,
        title: `Flagged ${c.subtype.toLowerCase()}`,
        detail: `${c.duration_seconds}s`,
        timestamp: c.timestamp,
        color: RISK_COLORS.Medium,
        href: null,
        rank: 6,
      })),
  ];

  return moments.sort((a, b) => a.rank - b.rank || Date.parse(b.timestamp) - Date.parse(a.timestamp));
}

const MAX_ROWS = 60;

export function NotableMoments({ data, selectedDay }: { data: GlobalTimeline; selectedDay: string | null }) {
  const moments = useMemo(() => {
    const all = buildMoments(data);
    const scoped = selectedDay ? all.filter((m) => m.timestamp.slice(0, 10) === selectedDay) : all;
    return scoped.slice(0, MAX_ROWS);
  }, [data, selectedDay]);

  const total = useMemo(() => {
    const all = buildMoments(data);
    return selectedDay ? all.filter((m) => m.timestamp.slice(0, 10) === selectedDay).length : all.length;
  }, [data, selectedDay]);

  return (
    <section className={styles.panel} aria-label="Notable moments">
      <header className={styles.header}>
        <span className={styles.title}>Notable moments</span>
        <span className={styles.count}>
          {total}
          {selectedDay ? ` on ${selectedDay}` : ""}
        </span>
      </header>

      {moments.length === 0 ? (
        <p className={styles.empty}>
          {selectedDay ? "Nothing flagged on this day." : "Nothing flagged in this range."}
        </p>
      ) : (
        <ul className={styles.list}>
          {moments.map((m) => {
            const body = (
              <>
                <span className={styles.severity} style={{ background: m.color }} aria-hidden />
                <span className={styles.body}>
                  <span className={styles.rowTitle}>{m.title}</span>
                  <span className={styles.rowDesc}>{m.detail}</span>
                  <span className={styles.rowMeta}>
                    {m.id} · {formatRelativeTime(m.timestamp)}
                  </span>
                </span>
                {m.href ? <ArrowUpRight size={14} className={styles.chevron} aria-hidden /> : null}
              </>
            );
            return (
              <li key={`${m.kind}-${m.id}`}>
                {m.href ? (
                  <Link href={m.href} className={styles.row}>
                    {body}
                  </Link>
                ) : (
                  // Flagged transactions and communications are relationships,
                  // not nodes — there is no page to open for one, so the row
                  // stays informational rather than pretending to be a link.
                  <div className={styles.rowStatic}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {total > moments.length ? (
        <p className={styles.more}>Showing {moments.length} of {total}</p>
      ) : null}
    </section>
  );
}
