"use client";

import { Map as MapIcon } from "lucide-react";
import { useState } from "react";
import { ArgusMap } from "@/components/map/ArgusMap";
import { MapControls } from "@/components/map/MapControls";
import { SelectedEntityPopup } from "@/components/map/SelectedEntityPopup";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PageShell } from "@/components/layout/PageShell";
import { useMapEntities, useMapShipments } from "@/hooks/useMap";
import type { GraphNode } from "@/lib/types";
import styles from "./page.module.css";

export default function MapPage() {
  const { data: entities, isLoading: loadingEntities } = useMapEntities();
  const { data: shipments, isLoading: loadingShipments } = useMapShipments();
  const [showEntities, setShowEntities] = useState(true);
  const [showShipments, setShowShipments] = useState(true);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const isLoading = loadingEntities || loadingShipments;

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
              onToggleEntities={() => setShowEntities((v) => !v)}
              onToggleShipments={() => setShowShipments((v) => !v)}
            />
            <ArgusMap
              entities={entities}
              shipments={shipments ?? []}
              showEntities={showEntities}
              showShipments={showShipments}
              onSelectEntity={setSelected}
            />
            {selected ? <SelectedEntityPopup node={selected} onClose={() => setSelected(null)} /> : null}
          </>
        )}
      </div>
    </PageShell>
  );
}
