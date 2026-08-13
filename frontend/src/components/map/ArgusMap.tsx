"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { HexagonLayer } from "@deck.gl/aggregation-layers";
import { ArcLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { GraphNode } from "@/lib/types";
import { riskTier } from "@/lib/theme";
import type { ShipmentRoute } from "@/hooks/useMap";
import styles from "./ArgusMap.module.css";

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const INDIA_CENTER: [number, number] = [79.5, 22.5];

// Zoom below which individual points give way to density hexagons — dumping
// thousands of raw points on screen at a country-wide zoom is exactly the
// clutter this redesign is meant to fix.
const HEX_ZOOM_THRESHOLD = 6.2;
const LABEL_ZOOM_THRESHOLD = 7.5;

const RISK_TIER_COLOR: Record<string, [number, number, number]> = {
  critical: [255, 59, 71],
  high: [255, 125, 26],
  medium: [255, 184, 0],
  low: [61, 123, 255],
  none: [61, 123, 255],
};
const ORG_COLOR: [number, number, number] = [168, 85, 247];
const ANOMALY_ARC: [number, number, number] = [255, 59, 71];
const NORMAL_ARC: [number, number, number] = [90, 100, 120];

function entityColor(node: GraphNode): [number, number, number] {
  const tier = riskTier(node.risk_score);
  if (tier === "critical" || tier === "high") return RISK_TIER_COLOR[tier];
  return node.label === "Organization" ? ORG_COLOR : RISK_TIER_COLOR.low;
}

export interface ArgusMapHandle {
  flyTo: (lng: number, lat: number) => void;
}

interface TooltipState {
  x: number;
  y: number;
  title: string;
  subtitle?: string;
}

interface ArgusMapProps {
  entities: GraphNode[];
  shipments: ShipmentRoute[];
  showEntities: boolean;
  showShipments: boolean;
  routeFilter: "anomalies" | "all";
  selectedEntityId: string | null;
  onSelectEntity: (node: GraphNode) => void;
  onSelectShipment: (shipment: ShipmentRoute) => void;
  onClusteredChange?: (clustered: boolean) => void;
}

export const ArgusMap = forwardRef<ArgusMapHandle, ArgusMapProps>(
  (
    { entities, shipments, showEntities, showShipments, routeFilter, selectedEntityId, onSelectEntity, onSelectShipment, onClusteredChange },
    ref,
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<MapLibreMap | null>(null);
    const overlayRef = useRef<MapboxOverlay | null>(null);
    const [zoom, setZoom] = useState(4.2);
    const [hovered, setHovered] = useState<TooltipState | null>(null);
    const zoomRafRef = useRef<number | null>(null);

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

      function scheduleZoomUpdate() {
        if (zoomRafRef.current !== null) return;
        zoomRafRef.current = requestAnimationFrame(() => {
          zoomRafRef.current = null;
          setZoom(map.getZoom());
        });
      }
      map.on("zoom", scheduleZoomUpdate);

      mapRef.current = map;
      overlayRef.current = overlay;

      return () => {
        if (zoomRafRef.current !== null) cancelAnimationFrame(zoomRafRef.current);
        map.remove();
        mapRef.current = null;
        overlayRef.current = null;
      };
    }, []);

    useEffect(() => {
      const overlay = overlayRef.current;
      if (!overlay) return;

      const layers = [];
      const useHex = zoom < HEX_ZOOM_THRESHOLD;
      const showLabels = zoom >= LABEL_ZOOM_THRESHOLD;
      onClusteredChange?.(useHex);

      if (showShipments) {
        if (routeFilter === "all") {
          layers.push(
            new ArcLayer<ShipmentRoute>({
              id: "shipments-normal",
              data: shipments.filter((s) => !s.route_anomaly),
              getSourcePosition: (d) => [d.origin_lng, d.origin_lat],
              getTargetPosition: (d) => [d.dest_lng, d.dest_lat],
              getSourceColor: NORMAL_ARC,
              getTargetColor: NORMAL_ARC,
              getWidth: 0.6,
              opacity: 0.22,
              greatCircle: true,
              pickable: false,
            }),
          );
        }
        layers.push(
          new ArcLayer<ShipmentRoute>({
            id: "shipments-anomaly",
            data: shipments.filter((s) => s.route_anomaly),
            getSourcePosition: (d) => [d.origin_lng, d.origin_lat],
            getTargetPosition: (d) => [d.dest_lng, d.dest_lat],
            getSourceColor: ANOMALY_ARC,
            getTargetColor: ANOMALY_ARC,
            getWidth: 2.5,
            opacity: 0.92,
            greatCircle: true,
            pickable: true,
            autoHighlight: true,
            highlightColor: [255, 255, 255, 100],
            onHover: (info) => {
              if (info.object) {
                setHovered({
                  x: info.x,
                  y: info.y,
                  title: `${info.object.origin_city} → ${info.object.dest_city}`,
                  subtitle: `${info.object.carrier} · anomalous route`,
                });
              } else {
                setHovered((prev) => (prev?.subtitle?.includes("route") ? null : prev));
              }
            },
            onClick: (info) => {
              if (info.object) onSelectShipment(info.object);
            },
          }),
        );
      }

      if (showEntities) {
        if (useHex) {
          layers.push(
            new HexagonLayer<GraphNode>({
              id: "entities-hex",
              data: entities,
              getPosition: (d) => [d.properties.lng, d.properties.lat],
              getColorWeight: (d) => d.risk_score,
              colorAggregation: "MAX",
              colorRange: [
                [61, 123, 255, 140],
                [61, 123, 255, 180],
                [255, 184, 0, 200],
                [255, 125, 26, 220],
                [255, 59, 71, 235],
                [255, 59, 71, 255],
              ],
              radius: 42_000,
              extruded: false,
              coverage: 0.85,
              pickable: true,
              // HexagonLayer's picked-object type isn't parameterized by the
              // layer's data type in this version of @deck.gl/aggregation-layers,
              // so its onHover/onClick signatures resolve to an unrelated
              // picking-info shape — the `any` here works around that upstream
              // type gap rather than fighting it with unsafe casts.
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              onHover: (info: any) => {
                const bin = info.object as { count?: number } | null;
                if (bin) {
                  setHovered({
                    x: info.x,
                    y: info.y,
                    title: `${bin.count ?? 0} entities`,
                    subtitle: "Click to zoom in",
                  });
                } else {
                  setHovered((prev) => (prev?.subtitle === "Click to zoom in" ? null : prev));
                }
                return true;
              },
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              onClick: (info: any) => {
                const map = mapRef.current;
                const bin = info.object as { position?: [number, number] } | null;
                if (map && bin?.position) {
                  map.flyTo({ center: bin.position, zoom: map.getZoom() + 2.4 });
                }
                return true;
              },
            }),
          );
        } else {
          layers.push(
            new ScatterplotLayer<GraphNode>({
              id: "entities",
              data: entities,
              getPosition: (d) => [d.properties.lng, d.properties.lat],
              getRadius: (d) => (d.id === selectedEntityId ? 7200 : d.risk_score >= 60 ? 5200 : 2600),
              getFillColor: entityColor,
              getLineColor: (d) => (d.id === selectedEntityId ? [240, 242, 247, 255] : [11, 12, 15, 180]),
              getLineWidth: (d) => (d.id === selectedEntityId ? 3 : 1),
              lineWidthUnits: "pixels",
              stroked: true,
              opacity: 0.85,
              pickable: true,
              autoHighlight: true,
              highlightColor: [255, 255, 255, 80],
              updateTriggers: {
                getRadius: [selectedEntityId],
                getLineColor: [selectedEntityId],
                getLineWidth: [selectedEntityId],
              },
              onHover: (info) => {
                if (info.object) {
                  setHovered({
                    x: info.x,
                    y: info.y,
                    title: info.object.name,
                    subtitle: `${info.object.label}${info.object.risk_score > 0 ? ` · risk ${info.object.risk_score}` : ""}`,
                  });
                } else {
                  setHovered((prev) => (prev && !prev.subtitle?.includes("route") && prev.subtitle !== "Click to zoom in" ? null : prev));
                }
              },
              onClick: (info) => {
                if (info.object) onSelectEntity(info.object);
              },
            }),
          );

          if (showLabels) {
            const labelData = entities.filter(
              (e) => e.id === selectedEntityId || riskTier(e.risk_score) === "critical",
            );
            layers.push(
              new TextLayer<GraphNode>({
                id: "entity-labels",
                data: labelData,
                getPosition: (d) => [d.properties.lng, d.properties.lat],
                getText: (d) => d.name,
                getSize: 12,
                getColor: [240, 242, 247, 235],
                getPixelOffset: [0, -14],
                fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
                fontWeight: 600,
                outlineWidth: 2,
                outlineColor: [11, 12, 15, 255],
                background: false,
              }),
            );
          }
        }
      }

      overlay.setProps({ layers });
    }, [entities, shipments, showEntities, showShipments, routeFilter, selectedEntityId, zoom, onSelectEntity, onSelectShipment, onClusteredChange]);

    useImperativeHandle(ref, () => ({
      flyTo(lng, lat) {
        mapRef.current?.flyTo({ center: [lng, lat], zoom: 8 });
      },
    }));

    return (
      <div className={styles.container}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        {hovered ? (
          <div className={styles.tooltip} style={{ left: hovered.x + 14, top: hovered.y + 14 }}>
            <div className={styles.tooltipTitle}>{hovered.title}</div>
            {hovered.subtitle ? <div className={styles.tooltipSubtitle}>{hovered.subtitle}</div> : null}
          </div>
        ) : null}
      </div>
    );
  },
);

ArgusMap.displayName = "ArgusMap";
