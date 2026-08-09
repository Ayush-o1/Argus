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
  onRowClick?: (row: T) => void;
}

/** Generic data table used across ARGUS instead of hand-rolled per-page
 * <table> markup — see docs/frontend.md. Keeps column alignment, borders,
 * and hover/click affordances consistent everywhere it's used. */
export function Table<T>({ columns, rows, getRowKey, onRowClick }: TableProps<T>) {
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
          {rows.map((row) => (
            <tr
              key={getRowKey(row)}
              className={cn(onRowClick && styles.rowClickable)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col) => (
                <td key={col.key} className={cn(col.align === "right" && styles.alignRight)}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
