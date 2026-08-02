import { BarChart3 } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function AnalyticsPage() {
  return (
    <PageShell title="Analytics Engine" subtitle="Graph algorithms, risk scores, and community detection">
      <EmptyState
        icon={BarChart3}
        title="No algorithms have run yet"
        description="PageRank, Louvain community detection, betweenness centrality, and cycle detection — all backed by Neo4j GDS — arrive in Phase 6."
      />
    </PageShell>
  );
}
