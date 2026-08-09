"use client";

import { Map as MapIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArgusMap, type ArgusMapHandle } from "@/components/map/ArgusMap";
import { MapControls, MapLegend } from "@/components/map/MapControls";
import { SelectedEntityPopup } from "@/components/map/SelectedEntityPopup";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import { useMapEntities, useMapShipments } from "@/hooks/useMap";
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
  const { data: entities, isLoading: loadingEntities } = useMapEntities();
  const { data: shipments, isLoading: loadingShipments } = useMapShipments();
  const [showEntities, setShowEntities] = useState(true);
  const [showShipments, setShowShipments] = useState(true);
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  // undefined = no manual selection yet, so the URL-focused entity (if any)
  // still wins; null = the popup was explicitly closed.
  const [manualSelection, setManualSelection] = useState<GraphNode | null | undefined>(undefined);
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

  return (
    <PageShell full>
      <div className={styles.wrap}>
        {isLoading ? (
          <div className={styles.centerState}>
            <Spinner size={28} />
          </div>
        ) : !entities || entities.length === 0 ? (
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
              showEntities={showEntities}
              showShipments={showShipments}
              highRiskOnly={highRiskOnly}
              onToggleEntities={() => setShowEntities((v) => !v)}
              onToggleShipments={() => setShowShipments((v) => !v)}
              onToggleHighRiskOnly={() => setHighRiskOnly((v) => !v)}
            />
            <ArgusMap
              ref={mapRef}
              entities={entities}
              shipments={shipments ?? []}
              showEntities={showEntities}
              showShipments={showShipments}
              highRiskOnly={highRiskOnly}
              onSelectEntity={setManualSelection}
            />
            <MapLegend />
            {selected ? <SelectedEntityPopup node={selected} onClose={() => setManualSelection(null)} /> : null}
          </>
        )}
      </div>
    </PageShell>
  );
}
