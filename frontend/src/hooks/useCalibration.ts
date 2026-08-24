import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type {
  CalibrationReport,
  ClassificationLevel,
  DriftReport,
  ExportAccess,
  ExportFormat,
  ExportRecord,
  FalseNegatives,
  SimulationResult,
} from "@/lib/calibration";

export function useCalibration() {
  return useQuery({
    queryKey: ["calibration"],
    queryFn: async () => (await apiFetch<CalibrationReport>("/api/calibration")).data,
  });
}

export function useFalseNegatives() {
  return useQuery({
    queryKey: ["calibration", "false-negatives"],
    queryFn: async () =>
      (await apiFetch<FalseNegatives>("/api/calibration/false-negatives")).data,
  });
}

export function useDrift() {
  return useQuery({
    queryKey: ["calibration", "drift"],
    queryFn: async () => (await apiFetch<DriftReport>("/api/calibration/drift")).data,
  });
}

/**
 * Run a candidate rule configuration against the stored findings.
 *
 * A mutation rather than a query even though it writes nothing to the domain:
 * it is an action a person takes deliberately, it is audited, and it must not
 * be re-fired by a cache refetch behind their back.
 */
export function useSimulate() {
  return useMutation({
    mutationFn: async (payload: Record<string, unknown>) =>
      (
        await apiFetch<SimulationResult>("/api/calibration/simulate", {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
  });
}

export function useClassifications() {
  return useQuery({
    queryKey: ["classifications"],
    staleTime: 30 * 60 * 1000,
    queryFn: async () =>
      (
        await apiFetch<{
          levels: ClassificationLevel[];
          default: string;
          scheme_note: string;
          retention_note: string;
        }>("/api/exports/classifications")
      ).data,
  });
}

export function useExports(investigationId?: string) {
  return useQuery({
    queryKey: ["exports", investigationId ?? ""],
    queryFn: async () => {
      const search = investigationId
        ? `?investigation_id=${encodeURIComponent(investigationId)}`
        : "";
      return apiFetch<ExportRecord[]>(`/api/exports${search}`);
    },
  });
}

export function useExportDetail(exportId: string | undefined) {
  return useQuery({
    queryKey: ["exports", "detail", exportId],
    enabled: !!exportId,
    queryFn: async () =>
      (
        await apiFetch<ExportRecord & { handling: string; access: ExportAccess[]; disposed: boolean }>(
          `/api/exports/${encodeURIComponent(exportId!)}`,
        )
      ).data,
  });
}

export function useCreateExport() {
  return useMutation({
    mutationFn: async (payload: {
      investigation_ref: string;
      format: ExportFormat;
      purpose: string;
    }) =>
      (
        await apiFetch<ExportRecord>("/api/exports", {
          method: "POST",
          body: JSON.stringify(payload),
        })
      ).data,
  });
}

export function useVerifyExport() {
  return useMutation({
    mutationFn: async (exportId: string) =>
      (
        await apiFetch<{
          export_id: string;
          intact: boolean;
          recorded_sha256: string;
          explains: string;
          disposed: boolean;
        }>(`/api/exports/${encodeURIComponent(exportId)}/verify`, { method: "POST" })
      ).data,
  });
}
