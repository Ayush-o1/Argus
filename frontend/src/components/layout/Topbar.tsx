"use client";

import { Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { UserMenu } from "@/components/auth/UserMenu";
import { useDashboardSummary } from "@/hooks/useDashboard";
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
  const { data: summary } = useDashboardSummary();
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

      <button type="button" className={styles.searchField} onClick={() => setCommandPaletteOpen(true)}>
        <Search size={14} />
        <span className={styles.searchPlaceholder}>Search entities, cases, alerts…</span>
        <span className={styles.kbd}>⌘K</span>
      </button>

      <div className={styles.actions}>
        {summary ? (
          <span className={styles.worldStat} title="Entities in the current synthetic world">
            {(summary.total_persons + summary.total_organizations).toLocaleString("en-IN")} entities
          </span>
        ) : null}
        {/* The product is explicitly a simulation over generated data. Stating
         * that once, quietly, in persistent chrome is more honest than either
         * hiding it or repeating a banner on every page. */}
        <span className={styles.simBadge} title="All data in this instance is procedurally generated. No real individuals or organizations are represented.">
          <span className={styles.simDot} />
          Synthetic
        </span>
        <UserMenu />
      </div>
    </header>
  );
}
