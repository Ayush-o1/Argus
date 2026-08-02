import { LayoutGrid } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function DashboardPage() {
  return (
    <PageShell title="Dashboard" subtitle="Command center overview">
      <EmptyState
        icon={LayoutGrid}
        title="No synthetic world generated yet"
        description="Stat cards, the alert queue, and the activity feed populate once the data generator has produced a world. This lands in Phase 1 of the build."
      />
    </PageShell>
  );
}
