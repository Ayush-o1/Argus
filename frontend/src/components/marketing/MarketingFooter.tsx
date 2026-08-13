import { ShieldHalf } from "lucide-react";
import Link from "next/link";
import styles from "./MarketingFooter.module.css";

export function MarketingFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div>
          <div className={styles.brand}>
            <span className={styles.brandMark}>
              <ShieldHalf size={13} strokeWidth={2} />
            </span>
            ARGUS
          </div>
          <p className={styles.disclaimer}>
            A graph-native investigation and analytics platform built entirely on procedurally
            generated synthetic data. No real individual or organization is represented — this is an
            engineering demonstration, not a surveillance tool.
          </p>
        </div>

        <div className={styles.links}>
          <div className={styles.linkGroup}>
            <span className={styles.linkGroupTitle}>Product</span>
            <Link href="/dashboard" className={styles.link}>
              Dashboard
            </Link>
            <Link href="/graph" className={styles.link}>
              Graph Explorer
            </Link>
            <Link href="/map" className={styles.link}>
              Map
            </Link>
          </div>
          <div className={styles.linkGroup}>
            <span className={styles.linkGroupTitle}>Project</span>
            <a href="https://github.com/Ayush-o1/Argus" target="_blank" rel="noreferrer" className={styles.link}>
              Source on GitHub
            </a>
            <a
              href="https://github.com/Ayush-o1/Argus#readme"
              target="_blank"
              rel="noreferrer"
              className={styles.link}
            >
              Documentation
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
