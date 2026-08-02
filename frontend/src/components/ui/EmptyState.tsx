import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, actions }: EmptyStateProps) {
  return (
    <div className={styles.wrap}>
      <div className={styles.icon}>
        <Icon size={22} strokeWidth={1.75} />
      </div>
      <div className={styles.title}>{title}</div>
      {description ? <p className={styles.description}>{description}</p> : null}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}
