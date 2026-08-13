"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { RISK_COLORS } from "@/lib/theme";
import { withinBounds, type MapBounds, type MapScale } from "@/components/map/ArgusMap";
import type { CountryRollup, RegionRollup } from "@/hooks/useMap";
import styles from "./MapContextPanel.module.css";

/**
 * The ranked companion to the map canvas.
 *
 * Bubbles answer "where", but comparing two similar circles across a world map
 * is a poor way to answer "which places carry the most elevated risk". Drawing
 * region names onto the canvas also collided with the basemap's own continent
 * labels. A ranked list solves both: it is scannable, sortable by the thing
 * that matters, and gives drill-down an explicit affordance instead of relying
 * on the analyst guessing that bubbles are clickable.
 */

const MAX_ROWS = 12;

function accentFor(elevated: number, avgRisk: number): string {
  if (elevated >= 4) return RISK_COLORS.Critical;
  if (elevated >= 1) return RISK_COLORS.High;
  if (avgRisk >= 8) return RISK_COLORS.Medium;
  return "#5685D6";
}

interface MapContextPanelProps {
  scale: MapScale;
  regions: RegionRollup[];
  countries: CountryRollup[];
  bounds: MapBounds | null;
  onFlyTo: (lng: number, lat: number, zoom: number) => void;
}

export function MapContextPanel({ scale, regions, countries, bounds, onFlyTo }: MapContextPanelProps) {
  if (scale === "local") return null;

  // Scoped to what is actually on screen. Listing every country in the world
  // after drilling into South Asia made the drill-down decorative — the map
  // moved but the panel kept offering Germany and Brazil. Filtering on the
  // viewport rather than on a remembered "active region" also stays correct
  // when the analyst pans or zooms freely instead of clicking through.
  const visibleCountries = countries.filter((c) => withinBounds(c.lng, c.lat, bounds));

  const rows =
    scale === "world"
      ? [...regions]
          // Elevated entities first, then route anomalies: volume is context,
          // escalation is the story. Ranking on elevated count alone buried
          // Central Asia, which carries no elevated entities but by far the
          // most off-lane routing — a different signal, not a weaker one.
          .sort(
            (a, b) =>
              b.elevated_count - a.elevated_count ||
              b.anomalous_routes - a.anomalous_routes ||
              b.entity_count - a.entity_count,
          )
          .map((r) => ({
            key: r.region,
            title: r.region,
            // Country count moved to the map tooltip: at this width a third
            // clause truncated mid-word, which lost the anomaly count entirely.
            meta: `${r.entity_count.toLocaleString()} entities`,
            elevated: r.elevated_count,
            accent: accentFor(r.elevated_count, r.avg_risk),
            extra: r.anomalous_routes > 0 ? `${r.anomalous_routes} anomalous routes` : null,
            fly: () => onFlyTo(r.lng, r.lat, r.zoom),
          }))
      : [...visibleCountries]
          .sort((a, b) => b.elevated_count - a.elevated_count || b.entity_count - a.entity_count)
          .slice(0, MAX_ROWS)
          .map((c) => ({
            key: c.country,
            title: c.country,
            meta: `${c.region} · ${c.entity_count.toLocaleString()}`,
            elevated: c.elevated_count,
            accent: accentFor(c.elevated_count, c.avg_risk),
            extra: null,
            fly: () => onFlyTo(c.lng, c.lat, 6.4),
          }));

  return (
    <aside className={styles.panel} aria-label={scale === "world" ? "Regions by risk" : "Countries by risk"}>
      <header className={styles.header}>
        <span className={styles.title}>{scale === "world" ? "Regions" : "Countries"}</span>
        <span className={styles.subtitle}>by elevated entities</span>
      </header>
      <ul className={styles.list}>
        {rows.map((row) => (
          <li key={row.key}>
            <button type="button" className={styles.row} onClick={row.fly}>
              <span className={styles.accent} style={{ background: row.accent }} aria-hidden />
              <span className={styles.body}>
                <span className={styles.rowTitle}>{row.title}</span>
                <span className={styles.rowMeta}>
                  {row.meta}
                  {row.extra ? <span className={styles.rowAlert}> · {row.extra}</span> : null}
                </span>
              </span>
              <span className={cn(styles.count, row.elevated > 0 && styles.countActive)}>{row.elevated}</span>
              <ChevronRight size={14} className={styles.chevron} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
