"use client";

import type { ReactNode } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import { Skeleton } from "@/components/ui/Skeleton";
import { useSession } from "@/hooks/useAuth";
import styles from "./AuthGate.module.css";

/**
 * Renders the app only for an authenticated session, and the sign-in form
 * otherwise.
 *
 * This is a rendering decision, not a security boundary — the server rejects
 * every unauthenticated request regardless of what the client chooses to draw.
 * Its job is to avoid showing an analyst a shell full of failed requests.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { data: session, isLoading, isError, refetch } = useSession();

  if (isLoading) {
    return (
      <div className={styles.centre}>
        <Skeleton height={120} width={320} />
      </div>
    );
  }

  if (isError) {
    // Distinct from "not signed in": the API could not be reached at all, and
    // presenting a login form here would invite the user to retype credentials
    // into something that cannot accept them.
    return (
      <div className={styles.centre}>
        <div className={styles.message}>
          <h2 className={styles.title}>ARGUS is unreachable</h2>
          <p className={styles.body}>
            The API did not respond. This is a connectivity failure, not a rejected sign-in.
          </p>
          <button type="button" className={styles.retry} onClick={() => void refetch()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!session) return <LoginForm />;

  return <>{children}</>;
}
