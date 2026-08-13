import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { GraphNode } from "@/lib/types";

export interface ShipmentRoute {
  shipment_id: string;
  carrier: string;
  status: string;
  route_anomaly: boolean;
  risk_score: number;
  origin_name: string;
  origin_city: string;
  origin_lat: number;
  origin_lng: number;
  dest_name: string;
  dest_city: string;
  dest_lat: number;
  dest_lng: number;
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
