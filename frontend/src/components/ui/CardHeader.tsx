import styles from "./CardHeader.module.css";

/**
 * A visible heading inside a `Card`.
 *
 * `Card` is a plain container whose `title` prop is the HTML tooltip
 * attribute, not a rendered heading — so a card that needs a heading has to
 * render one. This exists so the several places that do render the same thing
 * rather than each inventing their own markup.
 */
export function CardHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className={styles.header}>
      <h2 className={styles.title}>{title}</h2>
      {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
    </div>
  );
}
