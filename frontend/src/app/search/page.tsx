"use client";

import { Search as SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { EntityCard } from "@/components/entity/EntityCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageShell } from "@/components/layout/PageShell";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useSearch } from "@/hooks/useSearch";
import styles from "./page.module.css";

const FACET_TYPES = ["Person", "Organization", "Vehicle", "Location"];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<string[]>([]);
  const [riskMin, setRiskMin] = useState(0);
  const debouncedQuery = useDebouncedValue(query, 250);

  const { data, isFetching } = useSearch(debouncedQuery);

  const filtered = useMemo(() => {
    const results = data?.data ?? [];
    return results.filter((node) => {
      if (activeTypes.length > 0 && !activeTypes.includes(node.label)) return false;
      if (node.risk_score < riskMin) return false;
      return true;
    });
  }, [data, activeTypes, riskMin]);

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
          {query.trim().length === 0 ? (
            <EmptyState
              icon={SearchIcon}
              title="Search the graph"
              description="Type a name to find persons, organizations, vehicles, and locations across the synthetic world."
            />
          ) : isFetching ? (
            <div className={styles.resultsList}>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} height={68} />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState icon={SearchIcon} title="No results" description={`Nothing matches "${query}".`} />
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
