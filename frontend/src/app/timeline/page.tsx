import { Clock } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function TimelinePage() {
  return (
    <PageShell title="Timeline" subtitle="Temporal event analysis">
      <EmptyState
        icon={Clock}
        title="No events to plot yet"
        description="The VisX swim-lane timeline, temporal zooming, and burst detection arrive in Phase 5, once the generator has produced an event history."
      />
    </PageShell>
  );
}
