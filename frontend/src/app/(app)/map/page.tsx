"use client";

import { Map as MapIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArgusMap, type ArgusMapHandle } from "@/components/map/ArgusMap";
import { MapControls, MapLegend, type EntityTypeFilter, type RouteFilter } from "@/components/map/MapControls";
import { SelectedEntityPopup } from "@/components/map/SelectedEntityPopup";
import { ShipmentDetailPopup } from "@/components/map/ShipmentDetailPopup";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import { useMapEntities, useMapShipments, type ShipmentRoute } from "@/hooks/useMap";
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

  const [entityType, setEntityType] = useState<EntityTypeFilter>("all");
  const [riskFilter, setRiskFilter] = useState(0);
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("anomalies");
  const [showEntities, setShowEntities] = useState(true);
  const [showShipments, setShowShipments] = useState(true);

  const { data: rawEntities, isLoading: loadingEntities } = useMapEntities(entityType === "all" ? undefined : entityType);
  const { data: shipments, isLoading: loadingShipments } = useMapShipments();

  const entities = useMemo(
    () => (rawEntities ?? []).filter((e) => e.risk_score >= riskFilter),
    [rawEntities, riskFilter],
  );

  // undefined = no manual selection yet, so the URL-focused entity (if any)
  // still wins; null = the popup was explicitly closed.
  const [manualSelection, setManualSelection] = useState<GraphNode | null | undefined>(undefined);
  const [selectedShipment, setSelectedShipment] = useState<ShipmentRoute | null>(null);
  const [clustered, setClustered] = useState(false);
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
              riskFilter={riskFilter}
              onRiskFilterChange={setRiskFilter}
              routeFilter={routeFilter}
              onRouteFilterChange={setRouteFilter}
              showEntities={showEntities}
              showShipments={showShipments}
              onToggleEntities={() => setShowEntities((v) => !v)}
              onToggleShipments={() => setShowShipments((v) => !v)}
              onSearchSelect={handleSearchSelect}
              clusteredView={clustered}
            />
            <ArgusMap
              ref={mapRef}
              entities={entities}
              shipments={shipments ?? []}
              showEntities={showEntities}
              showShipments={showShipments}
              routeFilter={routeFilter}
              selectedEntityId={selected?.id ?? null}
              onSelectEntity={handleSelectEntity}
              onSelectShipment={handleSelectShipment}
              onClusteredChange={setClustered}
            />
            <MapLegend />
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
