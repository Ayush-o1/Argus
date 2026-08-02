import { Settings as SettingsIcon } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageShell } from "@/components/layout/PageShell";

export default function SettingsPage() {
  return (
    <PageShell title="Settings" subtitle="System configuration">
      <EmptyState
        icon={SettingsIcon}
        title="Settings arrive in the polish phase"
        description="Data seed controls, appearance, performance thresholds, and the synthetic-data disclaimer are built out in Phase 10, once every feature they configure exists."
      />
    </PageShell>
  );
}
