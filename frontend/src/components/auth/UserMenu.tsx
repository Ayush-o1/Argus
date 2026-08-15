"use client";

import { LogOut } from "lucide-react";
import { useLogout, useSession } from "@/hooks/useAuth";
import styles from "./UserMenu.module.css";

/**
 * Who you are signed in as, and how to stop being.
 *
 * The role is shown persistently and deliberately: in a system where what you
 * can see depends on your role, an analyst finding a surface missing should be
 * able to tell at a glance whether that is a permission or a fault.
 */
export function UserMenu() {
  const { data: session } = useSession();
  const logout = useLogout();

  if (!session) return null;

  return (
    <div className={styles.wrap}>
      <div className={styles.identity}>
        <span className={styles.name}>{session.user.display_name}</span>
        <span className={styles.role}>{session.user.role}</span>
      </div>
      <button
        type="button"
        className={styles.logout}
        onClick={() => void logout.mutateAsync()}
        disabled={logout.isPending}
        title="Sign out"
        aria-label="Sign out"
      >
        <LogOut size={14} />
      </button>
    </div>
  );
}
