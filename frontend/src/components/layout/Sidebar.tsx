"use client";

import { ChevronsLeft, ChevronsRight, ShieldHalf } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { NAV_GROUPS } from "@/lib/constants";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useUIStore } from "@/stores/uiStore";
import styles from "./Sidebar.module.css";

export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  // Shares the same "dashboard summary" query/cache the Dashboard page already
  // uses (30s staleTime) — mounting it here too costs zero extra requests on
  // any page where the dashboard has already been visited this session, and
  // is what lets the sidebar answer "what needs attention?" from any page.
  const { data: summary } = useDashboardSummary();

  return (
    <aside className={cn(styles.sidebar, collapsed && styles.collapsed)}>
      <div className={styles.brand}>
        <div className={styles.brandMark}>
          <ShieldHalf size={16} strokeWidth={2} />
        </div>
        {!collapsed && <span className={styles.brandName}>ARGUS</span>}
      </div>

      <nav className={styles.nav}>
        {NAV_GROUPS.map((group, i) => (
          <div key={group.title ?? i} className={styles.group}>
            {!collapsed && group.title ? <div className={styles.groupTitle}>{group.title}</div> : null}
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              const badgeCount = !collapsed && item.badgeKey === "alerts" ? summary?.open_alerts : undefined;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(styles.item, active && styles.itemActive)}
                  title={item.label}
                >
                  <span className={styles.itemIcon}>
                    <Icon size={17} strokeWidth={1.75} />
                  </span>
                  {!collapsed && <span className={styles.itemLabel}>{item.label}</span>}
                  {badgeCount ? <span className={styles.itemBadge}>{badgeCount}</span> : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <button
          type="button"
          className={styles.collapseButton}
          onClick={toggleSidebar}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}
