"use client";

import { useMemo, useRef, useState } from "react";
import { ArgusMap, type ArgusMapHandle, type MapScale } from "@/components/map/ArgusMap";
import { MapControls, MapLegend, type EntityTypeFilter, type RouteFilter } from "@/components/map/MapControls";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { Button } from "@/components/ui/Button";
import { matchesBand } from "@/lib/assessment";
import { useMapCorridors, useMapCountries, useMapEntities, useMapRegions, useMapShipments } from "@/hooks/useMap";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import popupStyles from "@/components/map/SelectedEntityPopup.module.css";

/**
 * The Map lens — the real ArgusMap (MapLibre + deck.gl) canvas, same reuse
 * pattern as GraphLens with GraphCanvas. `region` from the shared scope bus
 * narrows which entities are plotted, matching how Command's region filter
 * narrows the lead list.
 *
 * Live-wired (Phase 12): `useMapEntities`/`useMapShipments`/`useMapRegions`/
 * `useMapCountries`/`useMapCorridors` are the exact hooks the real `/map`
 * page uses — verified against the live backend at 4,400 real entities,
 * which `ArgusMap` (WebGL via deck.gl, not Cytoscape's canvas layout)
 * already renders on that page without a cap.
 *
 * `MapControls`/`MapLegend` are now reused directly (same component, same
 * props the real `/map` page passes) rather than left unwired — entity-type,
 * assessment-band and route filters, and the entity/route layer toggles all
 * behave identically to the old page. `MapContextPanel` (the drill-down
 * region/country/corridor browser) stays out of scope here: Command's own
 * region scope already does that narrowing for this lens. The popup is a
 * new, small component rather than a reuse of `SelectedEntityPopup`: that
 * component links to the old app's `/entities/:id` and `/graph?seed=`
 * routes, which would silently exit the `/next` experience on click. Its
 * CSS module is still reused as-is.
 */
export function MapLens() {
  const mapRef = useRef<ArgusMapHandle>(null);
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);
  const setFocus = useNextScopeStore((s) => s.setFocus);
  const setLens = useNextScopeStore((s) => s.setLens);
  const togglePin = useNextScopeStore((s) => s.togglePin);
  const pins = useNextScopeStore((s) => s.pins);
  const region = useNextScopeStore((s) => s.region);

  const [entityType, setEntityType] = useState<EntityTypeFilter>("all");
  const [bandFilter, setBandFilter] = useState("");
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("anomalies");
  const [showEntities, setShowEntities] = useState(true);
  const [showShipments, setShowShipments] = useState(true);
  const [scale, setScale] = useState<MapScale>("world");

  const { data: rawEntities } = useMapEntities(entityType === "all" ? undefined : entityType);
  const { data: shipments } = useMapShipments();
  const { data: regions } = useMapRegions();
  const { data: countries } = useMapCountries();
  const { data: corridors } = useMapCorridors();

  const entities = useMemo(() => {
    const byBand = (rawEntities ?? []).filter((e) => matchesBand(e.assessment?.band, bandFilter));
    return region ? byBand.filter((s) => s.properties.region === region) : byBand;
  }, [rawEntities, region, bandFilter]);

  const selected = selectedId ? (entities.find((e) => e.id === selectedId) ?? null) : null;

  return (
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
        onSearchSelect={(node) => select(node.id)}
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
        selectedEntityId={selectedId}
        onSelectEntity={(node) => select(node.id)}
        onSelectShipment={() => {}}
        onScaleChange={setScale}
      />
      <MapLegend scale={scale} />
      {selected ? (
        <div className={popupStyles.popup}>
          <div className={popupStyles.title}>{selected.name}</div>
          <div className={popupStyles.meta}>
            {selected.label} · {selected.properties.city}, {selected.properties.country}
          </div>
          <AssessmentBadge assessment={selected.assessment} />
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button
              variant="primary"
              size="sm"
              style={{ flex: 1 }}
              onClick={() => {
                setLens("graph");
                setFocus(selected.id);
              }}
            >
              Open in Graph
            </Button>
            <Button variant="secondary" size="sm" style={{ flex: 1 }} onClick={() => togglePin(selected.id)}>
              {pins.includes(selected.id) ? "Unpin" : "Pin"}
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={() => select(null)}>
            Close
          </Button>
        </div>
      ) : null}
    </>
  );
}
