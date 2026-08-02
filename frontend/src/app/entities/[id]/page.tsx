import { UserSearch } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default async function EntityProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <PageShell title="Entity Profile" subtitle={id}>
      <EmptyState
        icon={UserSearch}
        title="This entity does not exist yet"
        description="Entity profiles — properties, connections, activity timeline, and AI summary — render once the synthetic world has been generated (Phase 1) and the entity API is live (Phase 2/3)."
      />
    </PageShell>
  );
}
