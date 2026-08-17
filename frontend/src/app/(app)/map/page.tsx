"use client";

import { Map as MapIcon } from "lucide-react";
import { matchesBand } from "@/lib/assessment";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArgusMap, type ArgusMapHandle, type MapBounds, type MapScale } from "@/components/map/ArgusMap";
import { MapContextPanel } from "@/components/map/MapContextPanel";
import { MapControls, MapLegend, type EntityTypeFilter, type RouteFilter } from "@/components/map/MapControls";
import { SelectedEntityPopup } from "@/components/map/SelectedEntityPopup";
import { ShipmentDetailPopup } from "@/components/map/ShipmentDetailPopup";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import {
  useMapCorridors,
  useMapCountries,
  useMapEntities,
  useMapRegions,
  useMapShipments,
  type ShipmentRoute,
} from "@/hooks/useMap";
import type { GraphNode } from "@/lib/types";
import styles from "./page.module.css";

export default function MapPage() {
  return (
    <Suspense fallback={<PageShell full>{null}</PageShell>}>
      <MapPageInner />
    </Suspense>
  );
}

function MapPageInner() {
  const searchParams = useSearchParams();
  const focusId = searchParams.get("focus");
  const regionParam = searchParams.get("region");

  const [entityType, setEntityType] = useState<EntityTypeFilter>("all");
  const [bandFilter, setBandFilter] = useState("");
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("anomalies");
  const [showEntities, setShowEntities] = useState(true);
  const [showShipments, setShowShipments] = useState(true);

  const { data: rawEntities, isLoading: loadingEntities } = useMapEntities(entityType === "all" ? undefined : entityType);
  const { data: shipments, isLoading: loadingShipments } = useMapShipments();
  const { data: regions } = useMapRegions();
  const { data: countries } = useMapCountries();
  const { data: corridors } = useMapCorridors();

  const entities = useMemo(
    () => (rawEntities ?? []).filter((e) => matchesBand(e.assessment?.band, bandFilter)),
    [rawEntities, bandFilter],
  );

  // undefined = no manual selection yet, so the URL-focused entity (if any)
  // still wins; null = the popup was explicitly closed.
  const [manualSelection, setManualSelection] = useState<GraphNode | null | undefined>(undefined);
  const [selectedShipment, setSelectedShipment] = useState<ShipmentRoute | null>(null);
  const [scale, setScale] = useState<MapScale>("world");
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const mapRef = useRef<ArgusMapHandle>(null);

  const isLoading = loadingEntities || loadingShipments;

  // Arriving from an entity's "View on Map" link (Phase 7 cross-page
  // linking) — select that entity instead of leaving the analyst to find it
  // again among thousands of points. Derived rather than stored in state, so
  // there's nothing to keep in sync if `entities` finishes loading later.
  const focusedEntity = useMemo(() => entities?.find((e) => e.id === focusId) ?? null, [entities, focusId]);
  const selected = manualSelection !== undefined ? manualSelection : focusedEntity;

  useEffect(() => {
    if (focusedEntity) mapRef.current?.flyTo(focusedEntity.properties.lng, focusedEntity.properties.lat);
  }, [focusedEntity]);

  // Arriving from the dashboard's Global posture panel. This needs three
  // things to line up: the region rollup (for the target centre and zoom), a
  // mounted map, and a map that has finished loading its style — MapLibre
  // ignores flyTo before then. `bounds` is only set from the map's own load
  // and moveend events, so a non-null value is the readiness signal, and it is
  // in the dependency list so this re-runs once the map appears. Marking the
  // region as flown before the map existed made the link silently do nothing.
  const flownToRegion = useRef<string | null>(null);
  useEffect(() => {
    if (!regionParam || !regions || !bounds || flownToRegion.current === regionParam) return;
    const match = regions.find((r) => r.region === regionParam);
    if (!match || !mapRef.current) return;
    flownToRegion.current = regionParam;
    mapRef.current.flyToView(match.lng, match.lat, match.zoom);
  }, [regionParam, regions, bounds]);

  function handleSelectEntity(node: GraphNode) {
    setSelectedShipment(null);
    setManualSelection(node);
  }

  function handleSelectShipment(shipment: ShipmentRoute) {
    setManualSelection(null);
    setSelectedShipment(shipment);
  }

  function handleSearchSelect(node: GraphNode) {
    setSelectedShipment(null);
    setManualSelection(node);
    mapRef.current?.flyTo(node.properties.lng, node.properties.lat);
  }

  return (
    <PageShell full>
      <div className={styles.wrap}>
        {isLoading ? (
          <div className={styles.centerState}>
            <Spinner size={28} />
          </div>
        ) : !rawEntities || rawEntities.length === 0 ? (
          <div className={styles.centerState}>
            <EmptyState
              icon={MapIcon}
              title="No entities to place"
              description="Run the data generator to populate the world before exploring the map."
            />
          </div>
        ) : (
          <>
            <MapControls
              entityType={entityType}
              onEntityTypeChange={setEntityType}
              bandFilter={bandFilter}
              onBandFilterChange={setBandFilter}
              routeFilter={routeFilter}
              onRouteFilterChange={setRouteFilter}
              showEntities={showEntities}
              showShipments={showShipments}
              onToggleEntities={() => setShowEntities((v) => !v)}
              onToggleShipments={() => setShowShipments((v) => !v)}
              onSearchSelect={handleSearchSelect}
              scale={scale}
              onResetView={() => mapRef.current?.resetView()}
            />
            <ArgusMap
              ref={mapRef}
              entities={entities}
              shipments={shipments ?? []}
              regions={regions ?? []}
              countries={countries ?? []}
              corridors={corridors ?? []}
              showEntities={showEntities}
              showShipments={showShipments}
              routeFilter={routeFilter}
              selectedEntityId={selected?.id ?? null}
              onSelectEntity={handleSelectEntity}
              onSelectShipment={handleSelectShipment}
              onScaleChange={setScale}
              onBoundsChange={setBounds}
            />
            <MapContextPanel
              scale={scale}
              regions={regions ?? []}
              countries={countries ?? []}
              corridors={corridors ?? []}
              bounds={bounds}
              onFlyTo={(lng, lat, z) => mapRef.current?.flyToView(lng, lat, z)}
            />
            <MapLegend scale={scale} />
            {selected ? <SelectedEntityPopup node={selected} onClose={() => setManualSelection(null)} /> : null}
            {selectedShipment ? (
              <ShipmentDetailPopup shipment={selectedShipment} onClose={() => setSelectedShipment(null)} />
            ) : null}
          </>
        )}
      </div>
    </PageShell>
  );
}
