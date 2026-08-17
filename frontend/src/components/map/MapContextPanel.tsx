"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { RISK_COLOR_UNKNOWN, RISK_COLORS } from "@/lib/theme";
import { withinBounds, type MapBounds, type MapScale } from "@/components/map/ArgusMap";
import type { Corridor, CountryRollup, RegionRollup } from "@/hooks/useMap";
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

/** Keyed on how many entities ARGUS flagged and how many it could assess at
 * all — never on an average score. A region ARGUS could barely assess is drawn
 * as unknown rather than as calm. */
function accentFor(elevated: number, assessed: number): string {
  if (elevated >= 4) return RISK_COLORS.Critical;
  if (elevated >= 1) return RISK_COLORS.High;
  if (assessed === 0) return RISK_COLOR_UNKNOWN;
  return "#5685D6";
}

interface MapContextPanelProps {
  scale: MapScale;
  regions: RegionRollup[];
  countries: CountryRollup[];
  bounds: MapBounds | null;
  corridors: Corridor[];
  onFlyTo: (lng: number, lat: number, zoom: number) => void;
}

/**
 * The one thing worth saying about the current view, in a sentence.
 *
 * The map rendered its data faithfully but never stated a finding, so reading
 * it depended entirely on the analyst spotting the pattern themselves. Each
 * reading below is a direct comparison over values already on screen — the
 * region with the most off-lane routing, the busiest corridor — not a score or
 * a model output.
 */
function readingFor(
  scale: MapScale,
  regions: RegionRollup[],
  corridors: Corridor[],
  visibleCountries: CountryRollup[],
): string | null {
  if (scale === "world") {
    const byAnomaly = [...regions].sort((a, b) => b.flagged_routes - a.flagged_routes)[0];
    const byElevated = [...regions].sort((a, b) => b.elevated_count - a.elevated_count)[0];
    if (byElevated && byAnomaly && byElevated.elevated_count > 0 && byAnomaly.flagged_routes > 0) {
      // The interesting case is when escalation and routing anomalies sit in
      // different places — that mismatch is itself the finding.
      if (byAnomaly.region !== byElevated.region) {
        return `Elevated entities concentrate in ${byElevated.region}, but off-lane routing peaks on ${byAnomaly.region} (${byAnomaly.flagged_routes} flagged).`;
      }
      return `${byElevated.region} leads on both elevated entities (${byElevated.elevated_count}) and flagged routes (${byAnomaly.flagged_routes}).`;
    }
    const busiest = [...corridors].sort((a, b) => b.shipment_count - a.shipment_count)[0];
    if (busiest) {
      return `Heaviest corridor: ${busiest.from_region} to ${busiest.to_region} (${busiest.shipment_count} shipments).`;
    }
    return null;
  }

  // Scoped to what is on screen, matching the list beside it. Computing this
  // from the global region rollup meant that after drilling into South Asia the
  // panel listed South Asian countries under a sentence about the world's
  // leading region — the drill-down moved, the finding did not (audit B-16).
  const active = visibleCountries.filter((c) => c.elevated_count > 0);
  if (active.length === 0) {
    return visibleCountries.length > 0
      ? `No elevated entities among the ${visibleCountries.length} ${
          visibleCountries.length === 1 ? "country" : "countries"
        } in view.`
      : null;
  }
  const top = [...active].sort((a, b) => b.elevated_count - a.elevated_count)[0];
  const total = active.reduce((n, c) => n + c.elevated_count, 0);
  return active.length === 1
    ? `${top.country} carries all ${total} elevated ${total === 1 ? "entity" : "entities"} in view.`
    : `${top.country} holds ${top.elevated_count} of the ${total} elevated entities in view, across ${active.length} countries.`;
}

export function MapContextPanel({ scale, regions, countries, bounds, corridors, onFlyTo }: MapContextPanelProps) {
  if (scale === "local") return null;

  // Scoped to what is actually on screen. Listing every country in the world
  // after drilling into South Asia made the drill-down decorative — the map
  // moved but the panel kept offering Germany and Brazil. Filtering on the
  // viewport rather than on a remembered "active region" also stays correct
  // when the analyst pans or zooms freely instead of clicking through.
  const visibleCountries = countries.filter((c) => withinBounds(c.lng, c.lat, bounds));
  const reading = readingFor(scale, regions, corridors, visibleCountries);

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
              b.flagged_routes - a.flagged_routes ||
              b.entity_count - a.entity_count,
          )
          .map((r) => ({
            key: r.region,
            title: r.region,
            // Country count moved to the map tooltip: at this width a third
            // clause truncated mid-word, which lost the anomaly count entirely.
            meta: `${r.entity_count.toLocaleString()} entities`,
            elevated: r.elevated_count,
            accent: accentFor(r.elevated_count, r.assessed_count),
            extra: r.flagged_routes > 0 ? `${r.flagged_routes} flagged routes` : null,
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
            accent: accentFor(c.elevated_count, c.assessed_count),
            extra: null,
            fly: () => onFlyTo(c.lng, c.lat, 6.4),
          }));

  return (
    <aside className={styles.panel} aria-label={scale === "world" ? "Regions by risk" : "Countries by risk"}>
      <header className={styles.header}>
        <span className={styles.title}>{scale === "world" ? "Regions" : "Countries"}</span>
        <span className={styles.subtitle}>by elevated entities</span>
      </header>
      {reading ? <p className={styles.reading}>{reading}</p> : null}
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
