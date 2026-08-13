"use client";

import { Search as SearchIcon, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { EntityCard } from "@/components/entity/EntityCard";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
import { RangeSlider } from "@/components/ui/RangeSlider";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageShell } from "@/components/layout/PageShell";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useBrowseEntities } from "@/hooks/useEntities";
import { useSearch } from "@/hooks/useSearch";
import styles from "./page.module.css";

/** Matches the labels `list_entities` can page over. Location browses real
 * Locations now that the repository no longer collapses unknown types to
 * Person; Device is browse-only (it has no human name to full-text match). */
const FACET_TYPES = ["Person", "Organization", "Location", "Vehicle", "Device"];

const RISK_TICKS = ["0", "35", "60", "80", "100"];

function riskLabel(value: number): string {
  if (value === 0) return "Any";
  if (value >= 80) return "Critical only";
  if (value >= 60) return "High and above";
  if (value >= 35) return "Medium and above";
  return `${value}+`;
}

export default function SearchPage() {
  return (
    <Suspense fallback={<PageShell title="Search">{null}</PageShell>}>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<string[]>([]);
  // Entering from the dashboard's risk ladder pre-seeds the threshold, so the
  // click lands on a filtered result set rather than an empty search box.
  const [riskMin, setRiskMin] = useState(() => Number(params.get("risk") ?? 0) || 0);
  const debouncedQuery = useDebouncedValue(query, 250);

  const hasQuery = debouncedQuery.trim().length > 0;
  const hasFilters = activeTypes.length > 0 || riskMin > 0;
  // With no typed name, the type/risk filters used to render but do nothing —
  // the page just showed "type a name" regardless of what was checked. Now,
  // as soon as a filter is active, that becomes a real server-side browse
  // across the selected types (or all facet types if only risk is set).
  const browseMode = !hasQuery && hasFilters;

  const textSearch = useSearch(hasQuery ? debouncedQuery : "");
  const browse = useBrowseEntities(browseMode ? (activeTypes.length > 0 ? activeTypes : FACET_TYPES) : [], riskMin);

  const isFetching = hasQuery ? textSearch.isFetching : browse.isFetching;

  const filtered = useMemo(() => {
    if (browseMode) {
      return browse.data.filter((node) => activeTypes.length === 0 || activeTypes.includes(node.label));
    }
    const results = textSearch.data?.data ?? [];
    return results.filter((node) => {
      if (activeTypes.length > 0 && !activeTypes.includes(node.label)) return false;
      if (node.risk_score < riskMin) return false;
      return true;
    });
  }, [browseMode, browse.data, textSearch.data, activeTypes, riskMin]);

  // Counts come from the result set actually on screen, so a facet never
  // advertises a number the current query can't deliver.
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of filtered) counts[node.label] = (counts[node.label] ?? 0) + 1;
    return counts;
  }, [filtered]);

  function toggleType(type: string) {
    setActiveTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  function resetFilters() {
    setActiveTypes([]);
    setRiskMin(0);
  }

  return (
    <PageShell title="Search" subtitle="Find any entity across the synthetic world">
      <div className={styles.searchBar}>
        <SearchIcon size={17} color="var(--text-tertiary)" />
        <input
          className={styles.searchInput}
          placeholder="Search by name — person, organization, location, vehicle…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        {query ? (
          <button type="button" className={styles.clearBtn} onClick={() => setQuery("")} aria-label="Clear search">
            <X size={15} />
          </button>
        ) : null}
      </div>

      <div className={styles.layout}>
        <aside className={styles.filters}>
          <div className={styles.filterGroup}>
            <div className={styles.filterHead}>
              <span className={styles.filterTitle}>Entity type</span>
              {hasFilters ? (
                <button type="button" className={styles.clearLink} onClick={resetFilters}>
                  Reset
                </button>
              ) : null}
            </div>
            {FACET_TYPES.map((type) => (
              <Checkbox
                key={type}
                label={type}
                checked={activeTypes.includes(type)}
                onChange={() => toggleType(type)}
                count={typeCounts[type]}
              />
            ))}
          </div>

          <div className={styles.filterGroup}>
            <RangeSlider
              label="Minimum risk"
              value={riskMin}
              valueLabel={riskLabel(riskMin)}
              ticks={RISK_TICKS}
              riskRamp
              onChange={(e) => setRiskMin(Number(e.target.value))}
            />
          </div>
        </aside>

        <div>
          {!hasQuery && !hasFilters ? (
            <div className={styles.suggestions}>
              <span className={styles.suggestTitle}>Start an investigation</span>
              <p className={styles.suggestHint}>
                Search by name, or jump straight to a slice of the graph. Every result opens a full
                entity profile with its relationships, geography, and timeline.
              </p>
              <div className={styles.chipRow}>
                <button type="button" className={styles.chip} onClick={() => setRiskMin(80)}>
                  <span style={{ color: "var(--risk-critical)" }}>●</span> Critical-risk entities
                </button>
                <button type="button" className={styles.chip} onClick={() => setRiskMin(60)}>
                  <span style={{ color: "var(--risk-high)" }}>●</span> High risk and above
                </button>
                {["Organization", "Location", "Vehicle"].map((t) => (
                  <button key={t} type="button" className={styles.chip} onClick={() => toggleType(t)}>
                    <EntityTypeIcon label={t} size={13} /> Browse {t.toLowerCase()}s
                  </button>
                ))}
              </div>
            </div>
          ) : isFetching ? (
            <div className={styles.resultsList}>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} height={62} />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={SearchIcon}
              title="No results"
              description={hasQuery ? `Nothing matches "${query}".` : "No entities match these filters."}
            />
          ) : (
            <>
              <div className={styles.resultsHeader}>
                <span className={styles.resultsCount}>
                  <strong>{filtered.length}</strong> {filtered.length === 1 ? "result" : "results"}
                  {hasQuery ? ` for "${debouncedQuery}"` : " matching filters"}
                </span>
              </div>
              <div className={styles.resultsList}>
                {filtered.map((node) => (
                  <EntityCard key={node.uuid} node={node} />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}
