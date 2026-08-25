import { create } from "zustand";

/**
 * The shared investigation context for the `/next` experience — Phase 4 of
 * the redesign (ARGUS_PLAN.md).
 *
 * One store, read and written by Command, Investigate's three lenses,
 * Evidence, Triage and Report alike, so a selection made in the graph is the
 * same selection the timeline, the map and the evidence ledger already know
 * about — no per-component state to keep in sync by hand. Modelled on
 * `useUIStore` (`stores/uiStore.ts`) rather than introducing a second state
 * library; this is a second store because its lifecycle (cleared on
 * `clearAll`, scoped to one investigation) is genuinely different from
 * `uiStore`'s persistent app-chrome state, not because Zustand itself needed
 * replacing.
 *
 * `timeWindow` reuses the exact `{ start, end }` epoch-ms convention already
 * shipped in `TimelineFilters.zoomRange` (`components/timeline/timelineModel.ts`)
 * so the real Timeline lens's existing drag-to-zoom logic can write directly
 * into this store without a shape translation.
 *
 * Mode itself is deliberately NOT here — it lives in the URL (see
 * `lib/next/modeRouting.ts`), because a mode has to survive a refresh and be
 * deep-linkable, and only the URL can do that. Everything in this store is
 * exactly the context that should carry *across* a mode switch.
 */

export type NextMode = "command" | "investigate" | "evidence" | "triage" | "report";
export type NextLens = "graph" | "map" | "timeline";

interface NextScopeState {
  lens: NextLens;
  setLens: (lens: NextLens) => void;

  /** The subject currently under inspection — drives the Command dossier,
   * the Evidence ledger's subject, and the default Report scope. */
  selectedId: string | null;
  select: (id: string | null) => void;

  /** An isolated subject in the Graph lens — distinct from `selectedId`
   * because selecting a node and isolating its neighbourhood are different
   * gestures (isolate dims everything outside the cluster; select just
   * opens the dossier). Isolating always also selects. */
  focusId: string | null;
  setFocus: (id: string | null) => void;
  clearFocus: () => void;

  /** Subjects explicitly carried into Report. Order is display order. */
  pins: string[];
  togglePin: (id: string) => void;

  region: string | null;
  setRegion: (region: string | null) => void;
  clearRegion: () => void;

  timeWindow: { start: number; end: number } | null;
  setTimeWindow: (window: { start: number; end: number } | null) => void;
  clearTimeWindow: () => void;

  hypothesis: string;
  setHypothesis: (text: string) => void;

  /** Set when Triage opens an alert or investigation, so Investigate/Report
   * can show which one is in scope without re-deriving it from `selectedId`
   * (a subject can be selected with no open alert or investigation). Setting
   * these does not navigate — the Triage row's click handler does that,
   * alongside calling this. */
  activeAlertId: string | null;
  activeInvestigationRef: string | null;
  openAlert: (alertId: string, subjectId: string | null) => void;
  openInvestigation: (ref: string, subjectId: string | null) => void;

  /** Clears everything the Working Set rail shows — region, window,
   * hypothesis, pins — but deliberately leaves `selectedId` alone: "clear
   * the working set" and "leave what I'm looking at" are different intents,
   * matching the design's own `onClearAll`. */
  clearWorkingSet: () => void;

  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
}

export const useNextScopeStore = create<NextScopeState>((set) => ({
  lens: "graph",
  setLens: (lens) => set({ lens }),

  selectedId: null,
  select: (id) => set({ selectedId: id }),

  focusId: null,
  setFocus: (id) => set((s) => ({ focusId: id, selectedId: id ?? s.selectedId })),
  clearFocus: () => set({ focusId: null }),

  pins: [],
  togglePin: (id) =>
    set((s) => ({ pins: s.pins.includes(id) ? s.pins.filter((p) => p !== id) : [...s.pins, id] })),

  region: null,
  setRegion: (region) => set({ region }),
  clearRegion: () => set({ region: null }),

  timeWindow: null,
  setTimeWindow: (timeWindow) => set({ timeWindow }),
  clearTimeWindow: () => set({ timeWindow: null }),

  hypothesis: "",
  setHypothesis: (hypothesis) => set({ hypothesis }),

  activeAlertId: null,
  activeInvestigationRef: null,
  openAlert: (alertId, subjectId) =>
    set((s) => ({ activeAlertId: alertId, lens: "graph", selectedId: subjectId ?? s.selectedId, focusId: subjectId })),
  openInvestigation: (ref, subjectId) =>
    set((s) => ({ activeInvestigationRef: ref, lens: "graph", selectedId: subjectId ?? s.selectedId, focusId: subjectId })),

  clearWorkingSet: () => set({ region: null, timeWindow: null, hypothesis: "", pins: [] }),

  paletteOpen: false,
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
}));
