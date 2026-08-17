"use client";

import { Search as SearchIcon, X } from "lucide-react";
import { matchesBand } from "@/lib/assessment";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { EntityCard } from "@/components/entity/EntityCard";
import { EntityTypeIcon } from "@/components/entity/EntityTypeIcon";
import { Checkbox } from "@/components/ui/Checkbox";
import { EmptyState } from "@/components/ui/EmptyState";
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

// A band filter replaces the minimum-risk slider. The slider ranged over the
// generator's planted score, and a continuous control implied a precision the
// number never had. "Not assessable" is offered explicitly, because asking
// which entities ARGUS could not reach a view on is a real question a
// threshold could not express.
const BAND_OPTIONS = [
  { value: "", label: "Any" },
  { value: "elevated", label: "Elevated" },
  { value: "notable", label: "Notable and above" },
  { value: "routine", label: "Examined, nothing found" },
  { value: "insufficient_evidence", label: "Not assessable" },
];

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
  const [activeRegions, setActiveRegions] = useState<string[]>([]);
  // Entering from the dashboard pre-seeds the band, so the click lands on a
  // filtered result set rather than an empty search box.
  const [band, setBand] = useState(() => params.get("band") ?? "");
  const debouncedQuery = useDebouncedValue(query, 250);

  const hasQuery = debouncedQuery.trim().length > 0;
  const hasFilters = activeTypes.length > 0 || activeRegions.length > 0 || band !== "";
  // With no typed name, the type/band filters used to render but do nothing —
  // the page just showed "type a name" regardless of what was checked. Now,
  // as soon as a filter is active, that becomes a real server-side browse
  // across the selected types (or all facet types if only the band is set).
  const browseMode = !hasQuery && hasFilters;

  const textSearch = useSearch(hasQuery ? debouncedQuery : "");
  const browse = useBrowseEntities(browseMode ? (activeTypes.length > 0 ? activeTypes : FACET_TYPES) : [], band);

  const isFetching = hasQuery ? textSearch.isFetching : browse.isFetching;

  const browseData = browse.data;

  const filtered = useMemo(() => {
    const inRegion = (node: (typeof browseData)[number]) =>
      activeRegions.length === 0 || activeRegions.includes(String(node.properties.region ?? ""));

    if (browseMode) {
      return browseData.filter(
        (node) => (activeTypes.length === 0 || activeTypes.includes(node.label)) && inRegion(node),
      );
    }
    const results = textSearch.data?.data ?? [];
    return results.filter((node) => {
      if (activeTypes.length > 0 && !activeTypes.includes(node.label)) return false;
      if (!matchesBand(node.assessment?.band, band)) return false;
      return inRegion(node);
    });
  }, [browseMode, browseData, textSearch.data, activeTypes, activeRegions, band]);

  // Counts come from the result set actually on screen, so a facet never
  // advertises a number the current query can't deliver.
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of filtered) counts[node.label] = (counts[node.label] ?? 0) + 1;
    return counts;
  }, [filtered]);

  // Regions offered are only those present in the unfiltered result set, so
  // the facet can never advertise a region the current query cannot deliver.
  // Counts, however, must ignore the region filter itself — otherwise every
  // unselected region would read 0 the moment one was ticked.
  const regionCounts = useMemo(() => {
    const source = browseMode ? browseData : (textSearch.data?.data ?? []);
    const counts: Record<string, number> = {};
    for (const node of source) {
      if (activeTypes.length > 0 && !activeTypes.includes(node.label)) continue;
      if (!browseMode && !matchesBand(node.assessment?.band, band)) continue;
      const region = node.properties.region;
      if (region) counts[String(region)] = (counts[String(region)] ?? 0) + 1;
    }
    return counts;
  }, [browseMode, browseData, textSearch.data, activeTypes, band]);

  const availableRegions = useMemo(
    () => Object.keys(regionCounts).sort((a, b) => regionCounts[b] - regionCounts[a]),
    [regionCounts],
  );

  function toggleRegion(region: string) {
    setActiveRegions((prev) => (prev.includes(region) ? prev.filter((r) => r !== region) : [...prev, region]));
  }

  function toggleType(type: string) {
    setActiveTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  function resetFilters() {
    setActiveTypes([]);
    setActiveRegions([]);
    setBand("");
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

          {availableRegions.length > 0 ? (
            <div className={styles.filterGroup}>
              <div className={styles.filterHead}>
                <span className={styles.filterTitle}>Region</span>
              </div>
              {availableRegions.map((region) => (
                <Checkbox
                  key={region}
                  label={region}
                  checked={activeRegions.includes(region)}
                  onChange={() => toggleRegion(region)}
                  count={regionCounts[region]}
                />
              ))}
            </div>
          ) : null}

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="assessment-band">
              ARGUS assessment
            </label>
            <select
              id="assessment-band"
              className={styles.filterSelect}
              value={band}
              onChange={(e) => setBand(e.target.value)}
            >
              {BAND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
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
                <button type="button" className={styles.chip} onClick={() => setBand("elevated")}>
                  <span style={{ color: "var(--risk-critical)" }}>●</span> Elevated by ARGUS
                </button>
                <button
                  type="button"
                  className={styles.chip}
                  onClick={() => setBand("insufficient_evidence")}
                >
                  <span style={{ color: "var(--risk-unknown)" }}>●</span> Too little evidence to
                  assess
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
