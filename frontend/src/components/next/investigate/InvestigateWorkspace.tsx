"use client";

import { AssessmentBadge } from "@/components/ui/AssessmentBadge";
import { GraphLens } from "./GraphLens";
import { MapLens } from "./MapLens";
import { TimelineLens } from "./TimelineLens";
import { useEntity } from "@/hooks/useEntities";
import { useNextScopeStore, type NextLens } from "@/stores/nextScopeStore";
import styles from "./InvestigateWorkspace.module.css";

const LENSES: { key: NextLens; label: string }[] = [
  { key: "graph", label: "GRAPH" },
  { key: "map", label: "MAP" },
  { key: "timeline", label: "TIMELINE" },
];

/**
 * Investigate mode (ARGUS_PLAN.md Phase 5-7): one shared context — selection,
 * region, time window — viewed through three lenses. Switching lenses is a
 * store write (`lens`), not navigation, so the context in the header/strip
 * below never resets when a lens changes; each lens reads the same
 * `useNextScopeStore` selection independently.
 *
 * Live-wired (Phase 12): `useEntity(selectedId)` is the single-entity fetch
 * the old app's entity detail page uses — `selectedId` is now always a real
 * entity id (Command, Triage and Evidence all set it from live data), so a
 * single fetch-by-id here is simpler and more correct than trying to find
 * it inside whichever lens's own dataset happens to be loaded.
 */
export function InvestigateWorkspace() {
  const lens = useNextScopeStore((s) => s.lens);
  const setLens = useNextScopeStore((s) => s.setLens);
  const selectedId = useNextScopeStore((s) => s.selectedId);
  const region = useNextScopeStore((s) => s.region);
  const timeWindow = useNextScopeStore((s) => s.timeWindow);
  const pins = useNextScopeStore((s) => s.pins);
  const togglePin = useNextScopeStore((s) => s.togglePin);

  const { data: selected } = useEntity(selectedId ?? undefined);

  const scopeParts = [
    region ? `REGION ${region.toUpperCase()}` : null,
    timeWindow ? `${new Date(timeWindow.start).toISOString().slice(0, 10)} → ${new Date(timeWindow.end).toISOString().slice(0, 10)}` : null,
  ].filter(Boolean);

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.headerLabel}>INVESTIGATE</span>
        <div className={styles.headerDivider} />
        <span className={styles.headerTitle}>{selected ? selected.name : "No subject selected"}</span>
        {scopeParts.length ? <span className={styles.headerScope}>{scopeParts.join(" · ")}</span> : null}
        <div className={styles.headerSpacer} />
        <div className={styles.lensSwitcher} role="tablist" aria-label="Investigate lens">
          {LENSES.map((l) => (
            <button
              key={l.key}
              type="button"
              role="tab"
              aria-selected={lens === l.key}
              className={styles.lensButton}
              data-active={lens === l.key}
              onClick={() => setLens(l.key)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.canvas}>
        {lens === "graph" ? <GraphLens /> : null}
        {lens === "map" ? <MapLens /> : null}
        {lens === "timeline" ? <TimelineLens /> : null}
      </div>

      {selected ? (
        <div className={styles.selectedStrip}>
          <span className={styles.selectedName}>{selected.name}</span>
          <span className={styles.selectedMeta}>
            {selected.label} · {selected.properties.city}
          </span>
          <span className={styles.selectedScore}>
            <AssessmentBadge assessment={selected.assessment} />
          </span>
          <div className={styles.selectedSpacer} />
          <button type="button" className={styles.selectedAction} onClick={() => togglePin(selected.id)}>
            {pins.includes(selected.id) ? "UNPIN" : "PIN TO REPORT"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
