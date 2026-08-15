import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { ConnectorHealth, IngestFailure, IngestHealth } from "@/lib/ingest";

/**
 * Source health polls, because the thing it reports is whether something has
 * *stopped*. A page that only refreshes on navigation would show a feed as
 * healthy for as long as the analyst leaves the tab open — which is precisely
 * the window in which a silent failure does its damage.
 */
export function useIngestHealth() {
  return useQuery({
    queryKey: ["ingest-health"],
    queryFn: async () => (await apiFetch<IngestHealth>("/api/ingest/health")).data,
    refetchInterval: 15_000,
  });
}

export function useIngestFailures(connectorId?: string, includeResolved = false) {
  return useQuery({
    queryKey: ["ingest-failures", connectorId, includeResolved],
    queryFn: async () => {
      const search = new URLSearchParams();
      if (connectorId) search.set("connector_id", connectorId);
      if (includeResolved) search.set("include_resolved", "true");
      return (await apiFetch<IngestFailure[]>(`/api/ingest/failures?${search.toString()}`)).data;
    },
  });
}

export function useConnectorBatches(connectorId: string | null) {
  return useQuery({
    queryKey: ["ingest-batches", connectorId],
    enabled: !!connectorId,
    queryFn: async () =>
      (
        await apiFetch<
          {
            batch_id: number;
            started_at: string;
            finished_at: string | null;
            status: string;
            records_fetched: number;
            records_new: number;
            records_duplicate: number;
            records_failed: number;
            error: string | null;
          }[]
        >(`/api/ingest/connectors/${encodeURIComponent(connectorId!)}/batches`)
      ).data,
  });
}

function useIngestMutation<TArgs>(
  path: (args: TArgs) => string,
  body?: (args: TArgs) => unknown,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (args: TArgs) =>
      apiFetch(path(args), {
        method: "POST",
        body: body ? JSON.stringify(body(args)) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ingest-health"] });
      queryClient.invalidateQueries({ queryKey: ["ingest-failures"] });
      queryClient.invalidateQueries({ queryKey: ["ingest-batches"] });
    },
  });
}

export function useRunConnector() {
  return useIngestMutation<string>((id) => `/api/ingest/connectors/${encodeURIComponent(id)}/run`);
}

export function useQuarantineConnector() {
  return useIngestMutation<{ connectorId: string; reason: string }>(
    ({ connectorId }) => `/api/ingest/connectors/${encodeURIComponent(connectorId)}/quarantine`,
    ({ reason }) => ({ reason }),
  );
}

export function useReleaseConnector() {
  return useIngestMutation<string>(
    (id) => `/api/ingest/connectors/${encodeURIComponent(id)}/release`,
  );
}

export function useReplayFailure() {
  return useIngestMutation<number>((id) => `/api/ingest/failures/${id}/replay`);
}

export function useResolveFailure() {
  return useIngestMutation<{ failureId: number; resolution: string }>(
    ({ failureId }) => `/api/ingest/failures/${failureId}/resolve`,
    ({ resolution }) => ({ resolution }),
  );
}

/** Freshness expressed the way an operator reads it, with the source's own
 * declared expectation as the yardstick. A feed with no declared expectation
 * returns null rather than a guess — inventing a threshold produces invented
 * alerts. */
export function freshness(connector: ConnectorHealth): {
  label: string;
  tone: "ok" | "medium" | "critical" | "neutral";
} {
  if (connector.quarantined_at) return { label: "Quarantined", tone: "critical" };
  if (!connector.enabled) return { label: "Disabled", tone: "neutral" };
  if (!connector.last_success_at) return { label: "Never produced", tone: "critical" };

  const ageHours = (Date.now() - new Date(connector.last_success_at).getTime()) / 3_600_000;
  const label = ageHours < 1 ? "Under an hour ago" : `${ageHours.toFixed(1)}h ago`;
  if (connector.staleness_hours === null) return { label: `${label} · no expectation set`, tone: "neutral" };
  if (ageHours > connector.staleness_hours) return { label: `${label} · overdue`, tone: "critical" };
  if (ageHours > connector.staleness_hours * 0.75) return { label: `${label} · due soon`, tone: "medium" };
  return { label, tone: "ok" };
}
