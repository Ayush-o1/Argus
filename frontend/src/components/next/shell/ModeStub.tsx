import styles from "./ModeStub.module.css";

/**
 * Honest placeholder for a mode not yet built, rather than a blank screen or
 * a page that silently does nothing. Named after the real implementation
 * phase in ARGUS_PLAN.md that builds it, so it's traceable, not vague.
 */
export function ModeStub({ title, body, phase }: { title: string; body: string; phase: string }) {
  return (
    <div className={styles.wrap}>
      <span className={styles.badge}>NOT YET BUILT</span>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.body}>{body}</p>
      <p className={styles.phase}>{phase}</p>
    </div>
  );
}
