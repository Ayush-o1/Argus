import { Search } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function SearchPage() {
  return (
    <PageShell title="Search" subtitle="Global entity and event search">
      <EmptyState
        icon={Search}
        title="Nothing to search yet"
        description="Faceted search over entities and events depends on the Neo4j fulltext index built during data generation (Phase 1) and the search API (Phase 2/3)."
      />
    </PageShell>
  );
}
