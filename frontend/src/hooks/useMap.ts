import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { GraphNode } from "@/lib/types";

export type AnomalyKind = "off_lane" | "circuitous" | "manifest_shift";

export interface ShipmentRoute {
  shipment_id: string;
  carrier: string;
  status: string;
  /** ARGUS's own assessment of the shipment. The generator's `route_anomaly`
   * flag and `anomaly_kind` label are no longer served: they were the answer
   * key, and the map rendered them as discovered anomalies. */
  argus_band: string | null;
  argus_score: number | null;
  argus_coverage: number | null;
  lane: string | null;
  origin_region: string | null;
  destination_region: string | null;
  distance_km: number | null;
  detour_ratio: number | null;
  departure: string | null;
  arrival: string | null;
  manifest: string[] | null;
  origin_name: string;
  origin_city: string;
  origin_country: string | null;
  origin_lat: number;
  origin_lng: number;
  dest_name: string;
  dest_city: string;
  dest_country: string | null;
  dest_lat: number;
  dest_lng: number;
  // Only set on `circuitous` routes — the third-region port a shipment
  // unexpectedly called at. Drives the dog-leg rendering on the map.
  via_name: string | null;
  via_city: string | null;
  via_country: string | null;
  via_lat: number | null;
  via_lng: number | null;
}

export interface RegionRollup {
  region: string;
  entity_count: number;
  org_count: number;
  country_count: number;
  /** Entities ARGUS assessed as elevated, and how many it could assess at
   * all. There is no average: a mean over a region ARGUS mostly could not
   * assess describes nothing, and shading a map by one is how a
   * sparsely-collected region comes to look calm. */
  elevated_count: number;
  assessed_count: number;
  /** Shipments ARGUS assessed as elevated or notable, attributed to both
   * endpoints. Counted from ARGUS's own band, not the generator's
   * `route_anomaly` flag. */
  flagged_routes: number;
  lat: number;
  lng: number;
  zoom: number;
}

export interface CountryRollup {
  country: string;
  country_code: string;
  region: string;
  entity_count: number;
  elevated_count: number;
  assessed_count: number;
  lat: number;
  lng: number;
}

export interface Corridor {
  from_region: string;
  to_region: string;
  shipment_count: number;
  anomalous_count: number;
  anomaly_rate: number;
  from_lat: number;
  from_lng: number;
  to_lat: number;
  to_lng: number;
}

export function useMapEntities(entityType?: "Person" | "Organization") {
  return useQuery({
    queryKey: ["map", "entities", entityType ?? "all"],
    queryFn: async () =>
      (await apiFetch<GraphNode[]>(`/api/map/entities${entityType ? `?type=${entityType}` : ""}`)).data,
  });
}

export function useMapShipments() {
  return useQuery({
    queryKey: ["map", "shipments"],
    queryFn: async () => (await apiFetch<ShipmentRoute[]>("/api/map/shipments")).data,
  });
}

export function useMapRegions() {
  return useQuery({
    queryKey: ["map", "regions"],
    queryFn: async () => (await apiFetch<RegionRollup[]>("/api/map/regions")).data,
  });
}

export function useMapCountries() {
  return useQuery({
    queryKey: ["map", "countries"],
    queryFn: async () => (await apiFetch<CountryRollup[]>("/api/map/countries")).data,
  });
}

export function useMapCorridors() {
  return useQuery({
    queryKey: ["map", "corridors"],
    queryFn: async () => (await apiFetch<Corridor[]>("/api/map/corridors")).data,
  });
}
