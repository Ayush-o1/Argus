"use client";

import { Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { useUIStore } from "@/stores/uiStore";
import styles from "./Topbar.module.css";

function humanize(segment: string) {
  // Dynamic route segments are human-readable IDs like CASE-0026 or
  // PRS-0003296 — splitting on "-" for those turns them into "CASE 0026",
  // silently changing the ID's actual format. Only word-ish static route
  // segments (dashboard, graph, scenario, ...) get title-cased.
  if (/\d/.test(segment)) return segment.toUpperCase();
  return segment
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function Topbar() {
  const pathname = usePathname();
  const setCommandPaletteOpen = useUIStore((s) => s.setCommandPaletteOpen);
  const segments = pathname.split("/").filter(Boolean);

  return (
    <header className={styles.topbar}>
      <div className={styles.breadcrumbs}>
        {segments.length === 0 ? (
          <span className={styles.crumbActive}>Dashboard</span>
        ) : (
          segments.map((seg, i) => (
            <span key={seg + i} className={i === segments.length - 1 ? styles.crumbActive : styles.crumb}>
              {humanize(seg)}
              {i < segments.length - 1 && " / "}
            </span>
          ))
        )}
      </div>

      <div className={styles.actions}>
        <button type="button" className={styles.searchButton} onClick={() => setCommandPaletteOpen(true)}>
          <Search size={14} />
          <span>Search</span>
          <span className={styles.kbd}>⌘K</span>
        </button>
      </div>
    </header>
  );
}
