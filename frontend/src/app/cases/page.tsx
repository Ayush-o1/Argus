import { ShieldHalf } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function CasesPage() {
  return (
    <PageShell title="Cases" subtitle="Manage ongoing investigations">
      <EmptyState
        icon={ShieldHalf}
        title="No cases yet"
        description="Case creation, evidence pin boards, and the case workspace arrive in Phase 7, once there are entities and alerts worth investigating."
      />
    </PageShell>
  );
}
