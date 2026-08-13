import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./Table.module.css";

export interface TableColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
}

interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  /**
   * Destination for the row. Prefer this over `onRowClick` for navigation: it
   * renders a real anchor in the first column, so the row is reachable by
   * keyboard, can be opened in a new tab or copied from the context menu, and
   * is announced as a link. A row that only carries an onClick handler has
   * none of that — it is invisible to every one of those interactions.
   */
  getRowHref?: (row: T) => string;
  /** For non-navigational row actions (selection, expansion). */
  onRowClick?: (row: T) => void;
}

/** Generic data table used across ARGUS instead of hand-rolled per-page
 * <table> markup — see docs/frontend.md. Keeps column alignment, borders,
 * and hover/click affordances consistent everywhere it's used. */
export function Table<T>({ columns, rows, getRowKey, getRowHref, onRowClick }: TableProps<T>) {
  const interactive = Boolean(getRowHref || onRowClick);

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={cn(col.align === "right" && styles.alignRight)}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const href = getRowHref?.(row);
            return (
              <tr
                key={getRowKey(row)}
                className={cn(interactive && styles.rowClickable)}
                // Whole-row click stays as a convenience on top of the real
                // anchor, never as the only way in.
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col, i) => (
                  <td key={col.key} className={cn(col.align === "right" && styles.alignRight)}>
                    {href && i === 0 ? (
                      <Link href={href} className={styles.rowLink}>
                        {col.render(row)}
                      </Link>
                    ) : (
                      col.render(row)
                    )}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
