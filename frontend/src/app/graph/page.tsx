import { Waypoints } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function GraphPage() {
  return (
    <PageShell full>
      <EmptyState
        icon={Waypoints}
        title="Graph Explorer has no data to render yet"
        description="The Cytoscape.js canvas, algorithm panel, and node detail view arrive in Phase 4 — once entities and relationships exist to visualize."
      />
    </PageShell>
  );
}
