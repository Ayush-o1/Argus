import type { ReactNode } from "react";
import styles from "./PageShell.module.css";

interface PageShellProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  /** Full-bleed mode for canvas-style pages (Graph, Map) — no padding, no header. */
  full?: boolean;
}

export function PageShell({ title, subtitle, actions, children, full }: PageShellProps) {
  if (full) {
    return (
      <div className={styles.shell}>
        <div className={styles.full}>{children}</div>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <div className={styles.inner}>
        {(title || actions) && (
          <div className={styles.header}>
            <div className={styles.titleGroup}>
              {title ? <h1 className={styles.title}>{title}</h1> : null}
              {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
            </div>
            {actions ? <div className={styles.actions}>{actions}</div> : null}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
