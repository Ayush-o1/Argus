import { AlertTriangle } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function AlertsPage() {
  return (
    <PageShell title="Alerts" subtitle="System-detected anomalies awaiting review">
      <EmptyState
        icon={AlertTriangle}
        title="No alerts yet"
        description="Alerts are generated during Phase 1 (storyline injection) and served through Phase 7's alert queue — transaction bursts, communication clusters, and shell-ring detections, all synthetic."
      />
    </PageShell>
  );
}
