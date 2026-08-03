import styles from "./Tabs.module.css";

interface TabsProps {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className={styles.list}>
      {tabs.map((tab) => (
        <button
          key={tab}
          type="button"
          className={[styles.tab, tab === active && styles.tabActive].filter(Boolean).join(" ")}
          onClick={() => onChange(tab)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
