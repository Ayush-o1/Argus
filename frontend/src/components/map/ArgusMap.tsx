"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { bandLabel } from "@/lib/assessment";
import type { Layer } from "@deck.gl/core";
import { ArcLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { GraphNode } from "@/lib/types";
import { assessmentTier } from "@/lib/theme";
import type { Corridor, CountryRollup, RegionRollup, ShipmentRoute } from "@/hooks/useMap";
import styles from "./ArgusMap.module.css";

/** A route ARGUS assessed as worth a look. Replaces the generator's
 * `route_anomaly` flag, which the map drew as a discovered anomaly when it was
 * the label the generator had written on the shipment in the first place. */
function isFlaggedRoute(shipment: ShipmentRoute): boolean {
  return shipment.argus_band === "elevated" || shipment.argus_band === "notable";
}


const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// The world view is the entry point: the product models a global picture, so
// opening on one country would frame every investigation as local before the
// analyst has asked anything.
const WORLD_CENTER: [number, number] = [30, 22];
const WORLD_ZOOM = 1.6;

/**
 * Scale tiers. Each answers a different question, which is why the map swaps
 * datasets rather than just re-styling one: at world zoom an analyst is reading
 * "which regions are active", and 4,000 individual points cannot express that
 * no matter how they are drawn.
 */
export type MapScale = "world" | "regional" | "local";

const REGIONAL_ZOOM = 3.3;
const LOCAL_ZOOM = 5.8;
const LABEL_ZOOM = 7.2;

// Routes are drawn as straight chords (`greatCircle: false`). A true
// great-circle path between, say, Central Asia and North America crosses near
// the pole, which Web Mercator projects off the top of the viewport as a stray
// vertical line. ArcLayer's getHeight bows arcs along Z, so it projects flat in
// this top-down view and cannot be used to tame them either. These arcs
// abstract a trade relationship rather than claim a sailed route, so a chord is
// both more readable and more honest about what it represents.

// The generator injects route anomalies at a 3% base rate, so a threshold below
// that paints most corridors red and "anomalous" stops meaning anything. This
// sits meaningfully above the baseline.
const ELEVATED_ANOMALY_RATE = 0.045;

// Beyond this the world view becomes a hairball; the remaining lanes are
// long-tail volume that the region bubbles already account for.
const MAX_CORRIDORS = 18;

export function scaleForZoom(zoom: number): MapScale {
  if (zoom < REGIONAL_ZOOM) return "world";
  if (zoom < LOCAL_ZOOM) return "regional";
  return "local";
}

const RISK_TIER_COLOR: Record<string, [number, number, number]> = {
  critical: [255, 59, 71],
  high: [255, 125, 26],
  medium: [224, 168, 0],
  low: [100, 116, 139],
  none: [71, 85, 105],
};
const ORG_COLOR: [number, number, number] = [168, 85, 247];
const ANOMALY_ARC: [number, number, number] = [255, 59, 71];
const NORMAL_ARC: [number, number, number] = [90, 100, 120];
const CORRIDOR_ARC: [number, number, number] = [86, 133, 214];
const TEXT_COLOR: [number, number, number, number] = [240, 242, 247, 235];
const TEXT_OUTLINE: [number, number, number, number] = [11, 12, 15, 255];
const FONT_STACK = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";

// The design system's low-risk slate is deliberately quiet in the UI, but on a
// near-black basemap a 3.5px slate dot is effectively invisible — which hid the
// 4,000 persons and left the 400 organizations looking like the whole dataset.
// Map points get a lighter neutral so the baseline population is legible while
// still reading as unremarkable next to the risk tiers.
const PERSON_MAP_COLOR: [number, number, number] = [148, 163, 184];

function entityColor(node: GraphNode): [number, number, number] {
  const tier = assessmentTier(node.assessment?.band);
  if (tier === "critical" || tier === "high") return RISK_TIER_COLOR[tier];
  return node.label === "Organization" ? ORG_COLOR : PERSON_MAP_COLOR;
}

/** Aggregate colour: entities ARGUS assessed as elevated are the signal,
 * volume is just context. The third tier now keys on how much of the region
 * was assessable at all rather than on an average score — a region ARGUS could
 * barely assess should not read as a calm one. */
function rollupColor(elevated: number, assessed: number): [number, number, number] {
  if (elevated >= 4) return RISK_TIER_COLOR.critical;
  if (elevated >= 1) return RISK_TIER_COLOR.high;
  if (assessed === 0) return RISK_TIER_COLOR.none;
  return [86, 133, 214];
}

/** Area-proportional sizing — radius alone over-weights large aggregates. */
function bubbleRadius(count: number, scale: number): number {
  return Math.min(46, Math.max(7, Math.sqrt(count) * scale));
}

export interface ArgusMapHandle {
  flyTo: (lng: number, lat: number) => void;
  flyToView: (lng: number, lat: number, zoom: number) => void;
  resetView: () => void;
}

interface TooltipState {
  x: number;
  y: number;
  title: string;
  subtitle?: string;
  kind: "entity" | "route" | "aggregate";
}

interface ArgusMapProps {
  entities: GraphNode[];
  shipments: ShipmentRoute[];
  regions: RegionRollup[];
  countries: CountryRollup[];
  corridors: Corridor[];
  showEntities: boolean;
  showShipments: boolean;
  routeFilter: "anomalies" | "all";
  selectedEntityId: string | null;
  onSelectEntity: (node: GraphNode) => void;
  onSelectShipment: (shipment: ShipmentRoute) => void;
  onScaleChange?: (scale: MapScale) => void;
  onBoundsChange?: (bounds: MapBounds) => void;
}

/** [west, south, east, north] — the currently visible extent. */
export type MapBounds = [number, number, number, number];

export function withinBounds(lng: number, lat: number, b: MapBounds | null): boolean {
  if (!b) return true;
  const [west, south, east, north] = b;
  if (lat < south || lat > north) return false;
  // A viewport spanning the antimeridian has west > east.
  return west <= east ? lng >= west && lng <= east : lng >= west || lng <= east;
}

export const ArgusMap = forwardRef<ArgusMapHandle, ArgusMapProps>(function ArgusMap(
  {
    entities,
    shipments,
    regions,
    countries,
    corridors,
    showEntities,
    showShipments,
    routeFilter,
    selectedEntityId,
    onSelectEntity,
    onSelectShipment,
    onScaleChange,
    onBoundsChange,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [zoom, setZoom] = useState(WORLD_ZOOM);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [hovered, setHovered] = useState<TooltipState | null>(null);
  const zoomRafRef = useRef<number | null>(null);

  // Held in a ref so the map-construction effect stays mount-only; taking the
  // callback as a dependency would tear down and rebuild the whole map (and
  // refetch every basemap tile) whenever the parent re-rendered.
  const onBoundsChangeRef = useRef(onBoundsChange);
  onBoundsChangeRef.current = onBoundsChange;

  const scale = scaleForZoom(zoom);

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: WORLD_CENTER,
      zoom: WORLD_ZOOM,
      attributionControl: false,
      // Below this the world repeats horizontally and arcs render ambiguously.
      minZoom: 1.2,
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

    function reportBounds() {
      const b = map.getBounds();
      const next: MapBounds = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      setBounds(next);
      onBoundsChangeRef.current?.(next);
    }
    map.on("moveend", reportBounds);
    map.once("load", reportBounds);

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
    onScaleChange?.(scale);
  }, [scale, onScaleChange]);

  // A circuitous shipment is drawn as two legs through its via-port. Drawing it
  // as one origin->destination arc would hide the detour, which is the entire
  // reason the route was flagged.
  const routeSegments = useMemo(() => {
    let visible = routeFilter === "all" ? shipments : shipments.filter(isFlaggedRoute);
    // Once zoomed in, keep only routes that actually touch the visible extent.
    // Long intercontinental arcs merely transiting the viewport — both ends
    // off-screen — carry no information about the area being examined, and at
    // regional zoom they were the loudest thing on the map.
    if (scale !== "world" && bounds) {
      visible = visible.filter(
        (s) =>
          withinBounds(s.origin_lng, s.origin_lat, bounds) ||
          withinBounds(s.dest_lng, s.dest_lat, bounds) ||
          (s.via_lng != null && s.via_lat != null && withinBounds(s.via_lng, s.via_lat, bounds)),
      );
    }
    return visible.flatMap((s) => {
      if (s.via_lat != null && s.via_lng != null) {
        return [
          { shipment: s, from: [s.origin_lng, s.origin_lat] as [number, number], to: [s.via_lng, s.via_lat] as [number, number] },
          { shipment: s, from: [s.via_lng, s.via_lat] as [number, number], to: [s.dest_lng, s.dest_lat] as [number, number] },
        ];
      }
      return [
        { shipment: s, from: [s.origin_lng, s.origin_lat] as [number, number], to: [s.dest_lng, s.dest_lat] as [number, number] },
      ];
    });
  }, [shipments, routeFilter, scale, bounds]);

  // Corridors follow the same filter as individual routes, so the control means
  // the same thing at every scale. Defaulting to "anomalies" matters here:
  // drawing all 24 lanes between region centroids produced a tangle across the
  // middle of the map in which the few elevated corridors were invisible.
  const topCorridors = useMemo(() => {
    if (routeFilter === "anomalies") {
      return corridors.filter((c) => c.anomaly_rate > ELEVATED_ANOMALY_RATE);
    }
    return [...corridors].sort((a, b) => b.shipment_count - a.shipment_count).slice(0, MAX_CORRIDORS);
  }, [corridors, routeFilter]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;

    type Segment = (typeof routeSegments)[number];
    const layers: Layer[] = [];

    // --- Routes -----------------------------------------------------------
    // At world scale, individual shipments are replaced by corridor aggregates:
    // 1,200 arcs across a world map is texture, not information.
    if (showShipments && scale === "world") {
      layers.push(
        new ArcLayer<Corridor>({
          id: "corridors",
          data: topCorridors,
          getSourcePosition: (d) => [d.from_lng, d.from_lat],
          getTargetPosition: (d) => [d.to_lng, d.to_lat],
          getSourceColor: (d) => (d.anomaly_rate > ELEVATED_ANOMALY_RATE ? ANOMALY_ARC : CORRIDOR_ARC),
          getTargetColor: (d) => (d.anomaly_rate > ELEVATED_ANOMALY_RATE ? ANOMALY_ARC : CORRIDOR_ARC),
          getWidth: (d) => Math.min(9, 1.2 + Math.sqrt(d.shipment_count) * 0.45),
          widthUnits: "pixels",
          widthMinPixels: 1,
          widthMaxPixels: 9,
          opacity: 0.5,
          greatCircle: false,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 90],
          onHover: (info) => {
            if (info.object) {
              const d = info.object;
              setHovered({
                x: info.x,
                y: info.y,
                kind: "route",
                title: `${d.from_region} ↔ ${d.to_region}`,
                subtitle: `${d.shipment_count} shipments · ${d.anomalous_count} anomalous`,
              });
            } else {
              setHovered((prev) => (prev?.kind === "route" ? null : prev));
            }
          },
        }),
      );
    }

    if (showShipments && scale !== "world") {
      if (routeFilter === "all") {
        layers.push(
          new ArcLayer<Segment>({
            id: "shipments-normal",
            data: routeSegments.filter((s) => !isFlaggedRoute(s.shipment)),
            getSourcePosition: (d) => d.from,
            getTargetPosition: (d) => d.to,
            getSourceColor: NORMAL_ARC,
            getTargetColor: NORMAL_ARC,
            getWidth: 0.6,
            widthUnits: "pixels",
            widthMaxPixels: 1.5,
            opacity: 0.22,
            greatCircle: false,
            pickable: false,
          }),
        );
      }
      layers.push(
        new ArcLayer<Segment>({
          id: "shipments-anomaly",
          data: routeSegments.filter((s) => isFlaggedRoute(s.shipment)),
          getSourcePosition: (d) => d.from,
          getTargetPosition: (d) => d.to,
          getSourceColor: ANOMALY_ARC,
          getTargetColor: ANOMALY_ARC,
          getWidth: 2,
          widthUnits: "pixels",
          widthMinPixels: 1.25,
          widthMaxPixels: 2.5,
          // Saturated red at near-full opacity dominated the canvas at regional
          // zoom, where several long routes cross the whole viewport. Still
          // clearly the loudest thing on the map, without being the only thing.
          opacity: 0.78,
          greatCircle: false,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 100],
          onHover: (info) => {
            if (info.object) {
              const s = info.object.shipment;
              setHovered({
                x: info.x,
                y: info.y,
                kind: "route",
                title: `${s.origin_city} → ${s.dest_city}`,
                subtitle: `${s.carrier} · ${bandLabel(s.argus_band)}`,
              });
            } else {
              setHovered((prev) => (prev?.kind === "route" ? null : prev));
            }
          },
          onClick: (info) => {
            if (info.object) onSelectShipment(info.object.shipment);
          },
        }),
      );
    }

    // --- Entities ---------------------------------------------------------
    if (showEntities && scale === "world") {
      layers.push(
        new ScatterplotLayer<RegionRollup>({
          id: "regions",
          data: regions,
          getPosition: (d) => [d.lng, d.lat],
          getRadius: (d) => bubbleRadius(d.entity_count, 0.85),
          radiusUnits: "pixels",
          getFillColor: (d) => rollupColor(d.elevated_count, d.assessed_count),
          getLineColor: [11, 12, 15, 200],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          opacity: 0.82,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 70],
          onHover: (info) => {
            if (info.object) {
              const d = info.object;
              setHovered({
                x: info.x,
                y: info.y,
                kind: "aggregate",
                title: d.region,
                subtitle: `${d.entity_count.toLocaleString()} entities · ${d.country_count} countries · ${d.elevated_count} elevated`,
              });
            } else {
              setHovered((prev) => (prev?.kind === "aggregate" ? null : prev));
            }
          },
          onClick: (info) => {
            if (info.object) {
              mapRef.current?.flyTo({ center: [info.object.lng, info.object.lat], zoom: info.object.zoom, duration: 900 });
            }
          },
        }),
      );
    }

    if (showEntities && scale === "regional") {
      layers.push(
        new ScatterplotLayer<CountryRollup>({
          id: "countries",
          data: countries,
          getPosition: (d) => [d.lng, d.lat],
          getRadius: (d) => bubbleRadius(d.entity_count, 1.5),
          radiusUnits: "pixels",
          getFillColor: (d) => rollupColor(d.elevated_count, d.assessed_count),
          getLineColor: [11, 12, 15, 200],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          opacity: 0.8,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 70],
          onHover: (info) => {
            if (info.object) {
              const d = info.object;
              setHovered({
                x: info.x,
                y: info.y,
                kind: "aggregate",
                title: d.country,
                subtitle: `${d.entity_count.toLocaleString()} entities · ${d.elevated_count} elevated of ${d.assessed_count} assessed`,
              });
            } else {
              setHovered((prev) => (prev?.kind === "aggregate" ? null : prev));
            }
          },
          onClick: (info) => {
            if (info.object) {
              mapRef.current?.flyTo({ center: [info.object.lng, info.object.lat], zoom: 6.4, duration: 900 });
            }
          },
        }),
      );
    }

    if (showEntities && scale === "local") {
      layers.push(
        new ScatterplotLayer<GraphNode>({
          id: "entities",
          data: entities,
          getPosition: (d) => [d.properties.lng, d.properties.lat],
          getRadius: (d) =>
            d.id === selectedEntityId ? 8 : d.assessment?.band === "elevated" ? 6 : 3.5,
          radiusUnits: "pixels",
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
                kind: "entity",
                title: info.object.name,
                subtitle: `${info.object.label}${info.object.properties.country ? ` · ${info.object.properties.country}` : ""} · ${bandLabel(
                  info.object.assessment?.band,
                )}`,
              });
            } else {
              setHovered((prev) => (prev?.kind === "entity" ? null : prev));
            }
          },
          onClick: (info) => {
            if (info.object) onSelectEntity(info.object);
          },
        }),
      );

      if (zoom >= LABEL_ZOOM) {
        layers.push(
          new TextLayer<GraphNode>({
            id: "entity-labels",
            data: entities.filter(
              (e) => e.id === selectedEntityId || e.assessment?.band === "elevated",
            ),
            getPosition: (d) => [d.properties.lng, d.properties.lat],
            getText: (d) => d.name,
            getSize: 12,
            getColor: TEXT_COLOR,
            getPixelOffset: [0, -14],
            fontFamily: FONT_STACK,
            fontWeight: 600,
            outlineWidth: 2,
            outlineColor: TEXT_OUTLINE,
            background: false,
          }),
        );
      }
    }

    overlay.setProps({ layers });
  }, [
    entities,
    routeSegments,
    topCorridors,
    regions,
    countries,
    showEntities,
    showShipments,
    routeFilter,
    selectedEntityId,
    scale,
    zoom,
    onSelectEntity,
    onSelectShipment,
  ]);

  useImperativeHandle(ref, () => ({
    flyTo(lng, lat) {
      mapRef.current?.flyTo({ center: [lng, lat], zoom: 8, duration: 900 });
    },
    flyToView(lng, lat, targetZoom) {
      mapRef.current?.flyTo({ center: [lng, lat], zoom: targetZoom, duration: 900 });
    },
    resetView() {
      mapRef.current?.flyTo({ center: WORLD_CENTER, zoom: WORLD_ZOOM, duration: 900 });
    },
  }));

  return (
    <div className={styles.container}>
      <div
        ref={containerRef}
        role="graphics-document"
        aria-label={`World map, ${entities.length} entities and ${shipments.length} shipment routes plotted. Not screen-reader navigable; pan, zoom and selection are pointer-only.`}
        style={{ width: "100%", height: "100%" }}
      />
      {hovered ? (
        <div className={styles.tooltip} style={{ left: hovered.x + 14, top: hovered.y + 14 }}>
          <div className={styles.tooltipTitle}>{hovered.title}</div>
          {hovered.subtitle ? <div className={styles.tooltipSubtitle}>{hovered.subtitle}</div> : null}
        </div>
      ) : null}
    </div>
  );
});
