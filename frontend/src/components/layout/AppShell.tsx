import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import styles from "./AppShell.module.css";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.root}>
      <Sidebar />
      <div className={styles.main}>
        <Topbar />
        {children}
      </div>
    </div>
  );
}
