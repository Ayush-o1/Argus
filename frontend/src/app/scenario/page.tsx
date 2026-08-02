import { FlaskConical } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function ScenarioPage() {
  return (
    <PageShell title="Scenario Generator" subtitle="Create synthetic investigation scenarios on demand">
      <EmptyState
        icon={FlaskConical}
        title="Scenario generation isn't wired up yet"
        description="Shell company rings, money routing networks, and the other storyline types become generatable from this page in Phase 9, running as an async background job."
      />
    </PageShell>
  );
}
