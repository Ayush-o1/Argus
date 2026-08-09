"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { ArcLayer, ScatterplotLayer } from "@deck.gl/layers";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { GraphNode } from "@/lib/types";
import type { ShipmentRoute } from "@/hooks/useMap";

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const INDIA_CENTER: [number, number] = [79.5, 22.5];

const RISK_COLOR: [number, number, number] = [255, 59, 71]; // risk-critical
const BASE_COLOR: [number, number, number] = [61, 123, 255]; // accent-primary
const ORG_COLOR: [number, number, number] = [168, 85, 247]; // entity-organization
const ANOMALY_ARC: [number, number, number] = [255, 59, 71];
const NORMAL_ARC: [number, number, number] = [90, 100, 120];

export interface ArgusMapHandle {
  flyTo: (lng: number, lat: number) => void;
}

interface ArgusMapProps {
  entities: GraphNode[];
  shipments: ShipmentRoute[];
  showEntities: boolean;
  showShipments: boolean;
  highRiskOnly: boolean;
  onSelectEntity: (node: GraphNode) => void;
}

export const ArgusMap = forwardRef<ArgusMapHandle, ArgusMapProps>(
  ({ entities, shipments, showEntities, showShipments, highRiskOnly, onSelectEntity }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<MapLibreMap | null>(null);
    const overlayRef = useRef<MapboxOverlay | null>(null);

    useEffect(() => {
      if (!containerRef.current) return;

      const map = new maplibregl.Map({
        container: containerRef.current,
        style: DARK_STYLE,
        center: INDIA_CENTER,
        zoom: 4.2,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

      const overlay = new MapboxOverlay({ layers: [] });
      map.addControl(overlay as unknown as maplibregl.IControl);

      mapRef.current = map;
      overlayRef.current = overlay;

      return () => {
        map.remove();
        mapRef.current = null;
        overlayRef.current = null;
      };
    }, []);

    useEffect(() => {
      const overlay = overlayRef.current;
      if (!overlay) return;

      const layers = [];

      if (showShipments) {
        layers.push(
          new ArcLayer<ShipmentRoute>({
            id: "shipments",
            data: shipments,
            getSourcePosition: (d) => [d.origin_lng, d.origin_lat],
            getTargetPosition: (d) => [d.dest_lng, d.dest_lat],
            getSourceColor: (d) => (d.route_anomaly ? ANOMALY_ARC : NORMAL_ARC),
            getTargetColor: (d) => (d.route_anomaly ? ANOMALY_ARC : NORMAL_ARC),
            getWidth: (d) => (d.route_anomaly ? 2.5 : 1),
            greatCircle: true,
            pickable: false,
          }),
        );
      }

      if (showEntities) {
        const entityData = highRiskOnly ? entities.filter((e) => e.risk_score >= 60) : entities;
        layers.push(
          new ScatterplotLayer<GraphNode>({
            id: "entities",
            data: entityData,
            getPosition: (d) => [d.properties.lng, d.properties.lat],
            getRadius: (d) => (d.risk_score >= 60 ? 9000 : 4500),
            getFillColor: (d) => {
              if (d.risk_score >= 60) return RISK_COLOR;
              return d.label === "Organization" ? ORG_COLOR : BASE_COLOR;
            },
            opacity: 0.75,
            pickable: true,
            onClick: (info) => {
              if (info.object) onSelectEntity(info.object as GraphNode);
            },
          }),
        );
      }

      overlay.setProps({ layers });
    }, [entities, shipments, showEntities, showShipments, highRiskOnly, onSelectEntity]);

    useImperativeHandle(ref, () => ({
      flyTo(lng, lat) {
        mapRef.current?.flyTo({ center: [lng, lat], zoom: 8 });
      },
    }));

    return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
  },
);

ArgusMap.displayName = "ArgusMap";
