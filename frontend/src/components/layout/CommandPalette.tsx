"use client";

import { CornerDownLeft, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useSearch } from "@/hooks/useSearch";
import { cn } from "@/lib/cn";
import { NAV_GROUPS } from "@/lib/constants";
import { useUIStore } from "@/stores/uiStore";
import styles from "./CommandPalette.module.css";

interface FlatItem {
  label: string;
  href: string;
  group: string;
  icon?: (typeof NAV_GROUPS)[number]["items"][number]["icon"];
  /** Secondary line, e.g. an entity's type and ID. */
  meta?: string;
  /** Entity label (Person/Organization/…) when this row is a graph entity. */
  entityLabel?: string;
}

const FLAT_ITEMS: FlatItem[] = NAV_GROUPS.flatMap((group) =>
  group.items.map((item) => ({ label: item.label, href: item.href, group: group.title ?? "Navigate", icon: item.icon })),
);

/** Global "jump anywhere" command palette — ⌘K/Ctrl+K from any page. This
 * replaces the previous behavior of ⌘K hard-navigating straight to /search;
 * that made the shortcut a one-trick redirect instead of the fast, filterable
 * navigation surface an investigation tool like ARGUS benefits from. */
export function CommandPalette() {
  const open = useUIStore((s) => s.commandPaletteOpen);
  const setOpen = useUIStore((s) => s.setCommandPaletteOpen);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Every path that closes the palette goes through this, so query/selection
  // are always blank by the time it's next opened — no need to special-case
  // the closed->open transition with an effect or a ref read during render.
  function closePalette() {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
  }

  useEffect(() => {
    function onGlobalKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) closePalette();
        else setOpen(true);
      }
    }
    window.addEventListener("keydown", onGlobalKeyDown);
    return () => window.removeEventListener("keydown", onGlobalKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // Entity lookup is what makes this a genuine "jump to anything" surface
  // rather than a page switcher; pages stay in the list so navigation still
  // works, but real graph entities rank alongside them.
  const debouncedQuery = useDebouncedValue(query, 180);
  const entityQuery = debouncedQuery.trim().length > 1 ? debouncedQuery : "";
  const { data: entityData, isFetching } = useSearch(entityQuery);

  const results = useMemo<FlatItem[]>(() => {
    const q = query.trim().toLowerCase();
    const pages = q ? FLAT_ITEMS.filter((item) => item.label.toLowerCase().includes(q)) : FLAT_ITEMS;
    const entities: FlatItem[] = (entityData?.data ?? []).slice(0, 7).map((node) => ({
      label: node.name,
      href: `/entities/${node.id}`,
      group: "Entities",
      meta: `${node.label} · ${node.id}`,
      entityLabel: node.label,
    }));
    return [...pages, ...entities];
  }, [query, entityData]);

  function navigate(href: string) {
    router.push(href);
    closePalette();
  }

  function onKeyDown(e: ReactKeyboardEvent) {
    if (e.key === "Escape") {
      closePalette();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIndex]) {
      navigate(results[activeIndex].href);
    }
  }

  if (!open || typeof document === "undefined") return null;

  let lastGroup = "";

  return createPortal(
    <div className={styles.overlay} onClick={closePalette} role="presentation">
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label="Command palette" onClick={(e) => e.stopPropagation()}>
        <div className={styles.inputRow}>
          <Search size={16} />
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Search entities, or jump to a page…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onKeyDown}
          />
        </div>
        <div className={styles.list}>
          {results.length === 0 ? (
            <div className={styles.empty}>{isFetching ? "Searching…" : "No matching entities or pages"}</div>
          ) : (
            results.map((item, i) => {
              const showGroup = item.group !== lastGroup;
              lastGroup = item.group;
              const Icon = item.icon;
              return (
                <div key={`${item.group}-${item.href}`}>
                  {showGroup ? <div className={styles.groupLabel}>{item.group}</div> : null}
                  <button
                    type="button"
                    className={cn(styles.item, i === activeIndex && styles.itemActive)}
                    onMouseEnter={() => setActiveIndex(i)}
                    onClick={() => navigate(item.href)}
                  >
                    <span className={styles.itemIcon}>
                      {item.entityLabel ? (
                        <EntityTypeIcon label={item.entityLabel} size={14} />
                      ) : Icon ? (
                        <Icon size={15} />
                      ) : null}
                    </span>
                    <span className={styles.itemBody}>
                      <span className={styles.itemLabel}>{item.label}</span>
                      {item.meta ? <span className={styles.itemMeta}>{item.meta}</span> : null}
                    </span>
                  </button>
                </div>
              );
            })
          )}
        </div>
        <div className={styles.footer}>
          <span>
            <kbd>↑↓</kbd>navigate
          </span>
          <span>
            <CornerDownLeft size={11} style={{ verticalAlign: "-2px" }} /> select
          </span>
          <span>
            <kbd>esc</kbd>close
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
