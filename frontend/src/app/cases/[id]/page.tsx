import { ShieldHalf } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default async function CaseWorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <PageShell title="Case Workspace" subtitle={id}>
      <EmptyState
        icon={ShieldHalf}
        title="This case does not exist yet"
        description="The evidence board, markdown notes, AI case summary, and audit log arrive in Phase 7."
      />
    </PageShell>
  );
}
