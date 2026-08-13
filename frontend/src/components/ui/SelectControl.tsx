import { ChevronDown, type LucideIcon } from "lucide-react";
import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import styles from "./SelectControl.module.css";

interface SelectControlProps extends SelectHTMLAttributes<HTMLSelectElement> {
  icon?: LucideIcon;
  options: { value: string | number; label: string }[];
  /** Highlights the control when it holds a non-default value, so an active
   * filter is visible without opening the menu. */
  active?: boolean;
}

/** Toolbar-grade select. The app's canvas toolbars previously used bare
 * <select> elements, which render with the OS chrome and break the surface
 * language everywhere else in the product. */
export function SelectControl({ icon: Icon, options, active, className, ...props }: SelectControlProps) {
  return (
    <span className={styles.wrap}>
      {Icon ? (
        <span className={styles.icon}>
          <Icon size={14} />
        </span>
      ) : null}
      <select className={cn(styles.select, Icon && styles.withIcon, active && styles.active, className)} {...props}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span className={styles.chevron}>
        <ChevronDown size={13} />
      </span>
    </span>
  );
}
