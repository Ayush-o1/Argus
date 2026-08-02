import { Map as MapIcon } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function MapPage() {
  return (
    <PageShell full>
      <EmptyState
        icon={MapIcon}
        title="The map has no entities to place yet"
        description="MapLibre + deck.gl layers over real India geography arrive in Phase 5, once the generator has placed synthetic entities in real cities."
      />
    </PageShell>
  );
}
