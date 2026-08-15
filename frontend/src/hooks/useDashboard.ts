import { useQuery } from "@tanstack/react-query";
import { useHasPermission } from "@/hooks/useAuth";
import { apiFetch } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

/**
 * The dashboard aggregate, also used by the sidebar badges and the topbar
 * entity count.
 *
 * Gated on the permission because those two surfaces render on every page: for
 * a role without `entity:read` — an administrator, by design — the query fired
 * on every navigation and produced a stream of 403s in the console and
 * perpetual loading skeletons on screen. Not requesting what you are not
 * allowed to have is both quieter and more honest than requesting and failing.
 */
export function useDashboardSummary() {
  const canRead = useHasPermission("entity:read");

  return useQuery({
    queryKey: ["dashboard", "summary"],
    enabled: canRead,
    queryFn: async () => (await apiFetch<DashboardSummary>("/api/dashboard/summary")).data,
  });
}
