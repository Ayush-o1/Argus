"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { nextFixtureActivityDays, nextFixtureRegions, nextFixtureSubjects } from "@/lib/next/fixtures";
import { NEXT_MODE_PATH } from "@/lib/next/modeRouting";
import { useNextScopeStore, type NextMode } from "@/stores/nextScopeStore";
import styles from "./CommandBar.module.css";

interface CommandItem {
  group: "Actions" | "Geography" | "Entities" | "Modes";
  label: string;
  meta: string;
  icon: "entity" | "action";
  entityLabel?: string;
  run: () => void;
}

const MODE_DEFS: { key: NextMode; label: string }[] = [
  { key: "command", label: "Command" },
  { key: "investigate", label: "Investigate" },
  { key: "evidence", label: "Evidence" },
  { key: "triage", label: "Triage" },
  { key: "report", label: "Report" },
];

/**
 * Command Palette v2 (Phase 5) — an acting interface, not just navigation.
 *
 * Every command here invokes a real, already-working state transition on
 * `useNextScopeStore`; nothing here simulates a capability the app doesn't
 * have. Entity search runs against the fixture subject list rather than the
 * real `useSearch` hook for now, deliberately: everything else on screen
 * during the fixture phase is fixture data too, and a search that reached
 * into the real graph would return results nothing else on screen could
 * open. Both become real together in Phase 12.
 */
export function CommandBar() {
  const router = useRouter();
  const open = useNextScopeStore((s) => s.paletteOpen ?? false);
  const setOpen = useNextScopeStore((s) => s.setPaletteOpen);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const selectedId = useNextScopeStore((s) => s.selectedId);
  const select = useNextScopeStore((s) => s.select);
  const goToMode = (mode: NextMode) => router.push(NEXT_MODE_PATH[mode]);
  const setLens = useNextScopeStore((s) => s.setLens);
  const setFocus = useNextScopeStore((s) => s.setFocus);
  const togglePin = useNextScopeStore((s) => s.togglePin);
  const pins = useNextScopeStore((s) => s.pins);
  const setRegion = useNextScopeStore((s) => s.setRegion);
  const setTimeWindow = useNextScopeStore((s) => s.setTimeWindow);
  const clearTimeWindow = useNextScopeStore((s) => s.clearTimeWindow);

  // Resetting query/activeIndex happens at every *close*, not reactively on
  // `open` — the same practical effect (an empty palette next time it opens)
  // without a setState-in-effect: this component never unmounts while the
  // shell is mounted, so an effect watching `open` becoming true is a
  // response to a state change React already gave us a synchronous place to
  // handle (the code that closes it), not a synchronization with anything
  // external.
  function close() {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
    // Returns focus to whatever had it before the palette opened — the ⌘K
    // trigger button for a mouse click, but just as often nothing in
    // particular, since ⌘K is a global shortcut that can fire from anywhere.
    // Without this, focus is left on a node React is about to unmount, and
    // most browsers then silently drop it to <body> — a keyboard user closing
    // the palette would lose their place in the page entirely.
    previousFocusRef.current?.focus?.();
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) close();
        else setOpen(true);
      } else if (e.key === "Escape" && open) {
        close();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Focus only — no setState here, so this is a plain DOM synchronization
  // effect, not the pattern above.
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // A modal dialog must trap Tab — without this, tabbing forward from the
  // last result (or backward from the input) escapes into the page behind
  // the overlay, which a sighted keyboard user can no longer see is there.
  function trapTab(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab" || !dialogRef.current) return;
    const focusables = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("input, button:not(:disabled)"));
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const selected = nextFixtureSubjects.find((s) => s.id === selectedId) ?? null;
  const latestDay = nextFixtureActivityDays[nextFixtureActivityDays.length - 1]?.day;

  const items = useMemo<CommandItem[]>(() => {
    const list: CommandItem[] = [];

    if (selected) {
      list.push({
        group: "Actions",
        icon: "action",
        label: `Isolate ${selected.name} and its neighbourhood`,
        meta: "isolate",
        run: () => {
          setLens("graph");
          setFocus(selected.id);
          goToMode("investigate");
        },
      });
      list.push({
        group: "Actions",
        icon: "action",
        label: `Investigate ${selected.name}`,
        meta: "investigate",
        run: () => {
          setLens("graph");
          select(selected.id);
          goToMode("investigate");
        },
      });
      list.push({
        group: "Actions",
        icon: "action",
        label: `Inspect evidence for ${selected.name}`,
        meta: "evidence",
        run: () => goToMode("evidence"),
      });
      list.push({
        group: "Actions",
        icon: "action",
        label: `${pins.includes(selected.id) ? "Unpin" : "Pin"} ${selected.name} to the working set`,
        meta: "pin",
        run: () => togglePin(selected.id),
      });
    }

    if (latestDay) {
      list.push({
        group: "Actions",
        icon: "action",
        label: "Filter to the last 14 days",
        meta: "time",
        run: () => {
          const end = Date.parse(latestDay) + 86_400_000 - 1;
          setTimeWindow({ start: end - 14 * 86_400_000, end });
        },
      });
    }
    list.push({ group: "Actions", icon: "action", label: "Clear the time window", meta: "time", run: () => clearTimeWindow() });

    for (const r of nextFixtureRegions) {
      list.push({
        group: "Geography",
        icon: "action",
        label: `Scope to ${r.region}`,
        meta: `${r.elevated_count} elevated`,
        run: () => setRegion(r.region),
      });
    }

    for (const s of nextFixtureSubjects) {
      list.push({
        group: "Entities",
        icon: "entity",
        entityLabel: s.label,
        label: s.name,
        meta: `${s.label} · ${s.id}`,
        run: () => {
          select(s.id);
          goToMode("command");
        },
      });
    }

    for (const m of MODE_DEFS) {
      list.push({ group: "Modes", icon: "action", label: `Go to ${m.label}`, meta: m.key, run: () => goToMode(m.key) });
    }

    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, pins, latestDay, setLens, setFocus, select, togglePin, setTimeWindow, clearTimeWindow, setRegion]);

  const q = query.trim().toLowerCase();
  const filtered = q ? items.filter((it) => it.label.toLowerCase().includes(q) || it.meta.toLowerCase().includes(q)) : items;
  const results = filtered.slice(0, 24);

  if (!open) return null;

  function runActive() {
    const item = results[activeIndex];
    if (item) {
      item.run();
      close();
    }
  }

  let lastGroup = "";

  return (
    <div className={styles.overlay} onClick={close}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={trapTab}
      >
        <div className={styles.inputRow}>
          <span className={styles.prompt}>&gt;</span>
          <input
            ref={inputRef}
            className={styles.input}
            role="combobox"
            aria-expanded="true"
            aria-controls="next-command-results"
            aria-activedescendant={results[activeIndex] ? `next-command-result-${activeIndex}` : undefined}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(i + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter") {
                runActive();
              }
            }}
            placeholder="Find an entity, isolate a subject, filter time or geography, explain an elevation…"
          />
        </div>

        <div className={styles.results} id="next-command-results" role="listbox" aria-label="Command results">
          {results.map((it, i) => {
            const showGroup = it.group !== lastGroup;
            lastGroup = it.group;
            return (
              <div key={`${it.group}-${it.label}-${i}`}>
                {showGroup ? <div className={styles.groupLabel}>{it.group.toUpperCase()}</div> : null}
                <button
                  type="button"
                  id={`next-command-result-${i}`}
                  role="option"
                  aria-selected={i === activeIndex}
                  className={styles.resultRow}
                  data-active={i === activeIndex}
                  onMouseEnter={() => setActiveIndex(i)}
                  onClick={() => {
                    it.run();
                    close();
                  }}
                >
                  {it.icon === "entity" && it.entityLabel ? <EntityTypeIcon label={it.entityLabel} size={14} /> : <span className={styles.resultDot} />}
                  <span className={styles.resultLabel}>{it.label}</span>
                  <span className={styles.resultMeta}>{it.meta}</span>
                </button>
              </div>
            );
          })}
          {results.length === 0 ? <p className={styles.empty}>No matching action or entity.</p> : null}
        </div>

        <div className={styles.hints}>
          <span>↑↓ move</span>
          <span>⏎ run</span>
          <span>esc close</span>
          <span className={styles.hintsSpacer} />
          <span>actions apply to the working set</span>
        </div>
      </div>
    </div>
  );
}
