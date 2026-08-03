"use client";

import { Clock } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageShell } from "@/components/layout/PageShell";
import { TimelineChart } from "@/components/timeline/TimelineChart";
import { useGlobalTimeline } from "@/hooks/useTimeline";
import styles from "./page.module.css";

const LEGEND = [
  { label: "Flagged activity", color: "#FF3B47" },
  { label: "Baseline transactions", color: "#F97316" },
  { label: "Baseline communications", color: "#06B6D4" },
  { label: "Events", color: "#EC4899" },
];

export default function TimelinePage() {
  const { data, isLoading } = useGlobalTimeline();

  const totalFlagged =
    (data?.transactions.filter((t) => t.flagged).length ?? 0) + (data?.communications.filter((c) => c.flagged).length ?? 0);

  return (
    <PageShell
      title="Timeline"
      subtitle={
        data
          ? `${totalFlagged} flagged event${totalFlagged === 1 ? "" : "s"} against a baseline sample — spot the bursts`
          : "Temporal event analysis"
      }
    >
      {isLoading || !data ? (
        <Skeleton height={420} />
      ) : data.transactions.length === 0 && data.communications.length === 0 && data.events.length === 0 ? (
        <EmptyState icon={Clock} title="No activity yet" description="Run the data generator to populate the timeline." />
      ) : (
        <Card>
          <div className={styles.legend}>
            {LEGEND.map((item) => (
              <span key={item.label} className={styles.legendItem}>
                <span className={styles.dot} style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
          <TimelineChart data={data} />
        </Card>
      )}
    </PageShell>
  );
}
