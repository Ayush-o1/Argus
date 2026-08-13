"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useSearch } from "@/hooks/useSearch";
import type { GraphNode } from "@/lib/types";
import { EntityTypeIcon } from "./EntityTypeIcon";
import styles from "./EntitySearchBox.module.css";

interface EntitySearchBoxProps {
  onSelect: (node: GraphNode) => void;
  placeholder?: string;
}

export function EntitySearchBox({ onSelect, placeholder = "Find an entity…" }: EntitySearchBoxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const debounced = useDebouncedValue(query, 200);
  const wrapRef = useRef<HTMLDivElement>(null);

  const { data, isFetching } = useSearch(debounced.trim().length > 1 ? debounced : "");
  const results = data?.data ?? [];

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function handleSelect(node: GraphNode) {
    onSelect(node);
    setQuery("");
    setOpen(false);
  }

  const showDropdown = open && debounced.trim().length > 1;

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <div className={styles.inputRow}>
        <Search size={14} />
        <input
          className={styles.input}
          placeholder={placeholder}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
        />
        {query ? (
          <button
            type="button"
            className={styles.clearButton}
            onClick={() => {
              setQuery("");
              setOpen(false);
            }}
            aria-label="Clear search"
          >
            <X size={13} />
          </button>
        ) : null}
      </div>

      {showDropdown ? (
        <div className={styles.results}>
          {isFetching ? (
            <div className={styles.empty}>Searching…</div>
          ) : results.length === 0 ? (
            <div className={styles.empty}>No entities match &quot;{debounced}&quot;</div>
          ) : (
            results.slice(0, 8).map((node) => (
              <button key={node.id} type="button" className={styles.resultItem} onClick={() => handleSelect(node)}>
                <span className={styles.resultIcon}>
                  <EntityTypeIcon label={node.label} size={14} />
                </span>
                <span className={styles.resultBody}>
                  <div className={styles.resultName}>{node.name}</div>
                  <div className={styles.resultMeta}>
                    {node.label} · {node.id}
                  </div>
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
