import { Check } from "lucide-react";
import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import styles from "./Checkbox.module.css";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  /** Optional trailing count, e.g. the number of matches behind this filter. */
  count?: number;
}

/** Replaces the browser's native checkbox, whose default rendering reads as an
 * unstyled prototype next to the rest of the app's surfaces. */
export function Checkbox({ label, count, className, checked, ...props }: CheckboxProps) {
  return (
    <label className={cn(styles.wrap, className)}>
      <input type="checkbox" className={styles.input} checked={checked} {...props} />
      <span className={cn(styles.box, checked && styles.checked)}>
        <Check size={11} strokeWidth={3} />
      </span>
      <span className={styles.label}>{label}</span>
      {count !== undefined ? <span className={styles.count}>{count}</span> : null}
    </label>
  );
}
