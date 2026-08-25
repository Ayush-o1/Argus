"use client";

import { useMemo, useRef } from "react";
import { ArgusMap, type ArgusMapHandle } from "@/components/map/ArgusMap";
import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { Button } from "@/components/ui/Button";
import {
  nextFixtureCorridors,
  nextFixtureCountries,
  nextFixtureRegions,
  nextFixtureShipments,
  nextFixtureSubjects,
} from "@/lib/next/fixtures";
import { useNextScopeStore } from "@/stores/nextScopeStore";
import popupStyles from "@/components/map/SelectedEntityPopup.module.css";

/**
 * The Map lens — the real ArgusMap (MapLibre + deck.gl) canvas, fed fixture
 * entities/shipments/regions, same reuse pattern as GraphLens with
 * GraphCanvas. `region` from the shared scope bus narrows which entities are
 * plotted, matching how Command's region filter narrows the lead list.
 *
 * MapControls/MapLegend (entity-type and route filters on the real /map
 * page) aren't wired here yet — both layers are always on, all shipments
 * shown rather than anomalies-only. The popup is a new, small component
 * rather than a reuse of `SelectedEntityPopup`: that component links to the
 * old app's `/entities/:id` and `/graph?seed=` routes, which would silently
 * exit the `/next` experience on click. Its CSS module is still reused as-is.
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

  const entities = useMemo(
    () => (region ? nextFixtureSubjects.filter((s) => s.properties.region === region) : nextFixtureSubjects),
    [region],
  );

  const selected = selectedId ? (entities.find((e) => e.id === selectedId) ?? null) : null;

  return (
    <>
      <ArgusMap
        ref={mapRef}
        entities={entities}
        shipments={nextFixtureShipments}
        regions={nextFixtureRegions}
        countries={nextFixtureCountries}
        corridors={nextFixtureCorridors}
        showEntities
        showShipments
        routeFilter="all"
        selectedEntityId={selectedId}
        onSelectEntity={(node) => select(node.id)}
        onSelectShipment={() => {}}
      />
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
