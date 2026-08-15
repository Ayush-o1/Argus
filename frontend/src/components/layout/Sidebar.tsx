"use client";

import { ChevronsLeft, ChevronsRight, ShieldHalf, SquareArrowOutUpRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { NAV_GROUPS } from "@/lib/constants";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useSession } from "@/hooks/useAuth";
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
  const { data: session } = useSession();

  // Hide what this role cannot use. An administrator holds no
  // intelligence-read permission by design, so they see an administrative
  // sidebar rather than a wall of links that would all 403.
  const permitted = (permission?: string) =>
    !permission || (session?.permissions.includes(permission) ?? false);

  return (
    <aside className={cn(styles.sidebar, collapsed && styles.collapsed)}>
      {/* The brand returns to the application home, not the marketing page.
          That is the convention in every comparable product, and the inverse
          would eject an analyst out of the workspace mid-investigation from
          the one control they are most likely to click by reflex. The route
          back to the product overview is an explicit, labelled item in the
          footer instead — see below. */}
      <Link href="/dashboard" className={styles.brand} aria-label="ARGUS — go to Command Center">
        <span className={styles.brandMark}>
          <ShieldHalf size={16} strokeWidth={2} />
        </span>
        {!collapsed && <span className={styles.brandName}>ARGUS</span>}
      </Link>

      <nav className={styles.nav}>
        {NAV_GROUPS.map((group) => ({ group, items: group.items.filter((item) => permitted(item.permission)) }))
          // A group header with nothing under it is visual noise that reads as a
          // failed load rather than an absent permission.
          .filter(({ items }) => items.length > 0)
          .map(({ group, items }) => (
          <div key={group.title ?? items[0].href} className={styles.group}>
            {!collapsed && group.title ? <div className={styles.groupTitle}>{group.title}</div> : null}
            {items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              const count =
                item.badgeKey === "alerts"
                  ? summary?.open_alerts
                  : item.badgeKey === "cases"
                    ? summary?.active_cases
                    : undefined;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(styles.item, active && styles.itemActive)}
                  title={item.hint ? `${item.label} — ${item.hint}` : item.label}
                  aria-current={active ? "page" : undefined}
                >
                  <span className={styles.itemIcon}>
                    <Icon size={17} strokeWidth={1.75} />
                  </span>
                  {!collapsed && <span className={styles.itemLabel}>{item.label}</span>}
                  {count ? (
                    <span className={cn(styles.itemBadge, item.badgeKey === "alerts" && styles.itemBadgeAlert)}>
                      {count}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        {/* Deliberately separated from the investigation nav above: this leaves
            the workspace rather than moving within it, so it must not read as
            another destination in the same list. */}
        <Link
          href="/"
          className={styles.exitLink}
          title="Product overview — leaves the workspace"
        >
          <span className={styles.itemIcon}>
            <SquareArrowOutUpRight size={15} strokeWidth={1.75} />
          </span>
          {!collapsed && <span className={styles.itemLabel}>Product overview</span>}
        </Link>
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
