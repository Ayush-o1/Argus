import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { PatternModel, SpatialAnalysis, TemporalAnalysis } from "@/lib/patterns";

export function useTemporalPatterns(windowDays = 30, baselineDays = 90) {
  return useQuery({
    queryKey: ["patterns", "temporal", windowDays, baselineDays],
    queryFn: async () =>
      (
        await apiFetch<TemporalAnalysis>(
          `/api/patterns/temporal?window_days=${windowDays}&baseline_days=${baselineDays}`,
        )
      ).data,
  });
}

export function useSpatialPatterns(params: {
  epsKm?: number;
  minSamples?: number;
  bandKm?: number;
  value?: string;
} = {}) {
  const search = new URLSearchParams();
  if (params.epsKm) search.set("eps_km", String(params.epsKm));
  if (params.minSamples) search.set("min_samples", String(params.minSamples));
  if (params.bandKm) search.set("band_km", String(params.bandKm));
  if (params.value) search.set("value", params.value);
  const qs = search.toString();
  return useQuery({
    queryKey: ["patterns", "spatial", qs],
    queryFn: async () =>
      (await apiFetch<SpatialAnalysis>(`/api/patterns/spatial${qs ? `?${qs}` : ""}`)).data,
  });
}

export function usePatternModel() {
  return useQuery({
    queryKey: ["patterns", "model"],
    staleTime: 5 * 60 * 1000,
    queryFn: async () => (await apiFetch<PatternModel>("/api/patterns/model")).data,
  });
}
