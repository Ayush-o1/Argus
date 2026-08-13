"use client";

import { Search as SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { EntityCard } from "@/components/entity/EntityCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageShell } from "@/components/layout/PageShell";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useBrowseEntities } from "@/hooks/useEntities";
import { useSearch } from "@/hooks/useSearch";
import styles from "./page.module.css";

const FACET_TYPES = ["Person", "Organization", "Vehicle", "Location"];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<string[]>([]);
  const [riskMin, setRiskMin] = useState(0);
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

  function toggleType(type: string) {
    setActiveTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  return (
    <PageShell title="Search" subtitle="Global entity search">
      <div className={styles.searchBar}>
        <SearchIcon size={18} color="var(--text-tertiary)" />
        <input
          className={styles.searchInput}
          placeholder="Search entities by name..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>

      <div className={styles.layout}>
        <aside className={styles.filters}>
          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Type</span>
            {FACET_TYPES.map((type) => (
              <label key={type} className={styles.checkboxRow}>
                <input type="checkbox" checked={activeTypes.includes(type)} onChange={() => toggleType(type)} />
                {type}
              </label>
            ))}
          </div>
          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Min Risk Score</span>
            <input
              type="range"
              min={0}
              max={100}
              value={riskMin}
              onChange={(e) => setRiskMin(Number(e.target.value))}
            />
            <span className={styles.checkboxRow}>{riskMin}+</span>
          </div>
        </aside>

        <div>
          {!hasQuery && !hasFilters ? (
            <EmptyState
              icon={SearchIcon}
              title="Search the graph"
              description="Type a name, or check a type / set a minimum risk score to browse, to find persons, organizations, vehicles, and locations across the synthetic world."
            />
          ) : isFetching ? (
            <div className={styles.resultsList}>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} height={68} />
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
                {filtered.length} result{filtered.length === 1 ? "" : "s"}
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
