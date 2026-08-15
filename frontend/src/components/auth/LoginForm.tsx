"use client";

import { ShieldHalf } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useLogin } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";
import styles from "./LoginForm.module.css";

/**
 * The sign-in surface.
 *
 * Deliberately says as little as possible about failures. The backend returns
 * one message for "no such user", "wrong password" and "account locked"; the
 * form does not try to be more helpful, because distinguishing them hands an
 * attacker a free account-enumeration oracle. The one exception is the MFA
 * prompt, which is only reachable once the password has already been verified.
 */
export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useLogin();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      await login.mutateAsync({
        username,
        password,
        ...(needsMfa ? { mfa_code: mfaCode } : {}),
      });
      // On success the session query updates and the shell re-renders; there is
      // nothing to navigate to.
    } catch (err) {
      if (err instanceof ApiError && err.detail === "mfa_required") {
        setNeedsMfa(true);
        setError(null);
        return;
      }
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Wait a minute before trying again.");
        return;
      }
      setError(err instanceof ApiError ? (err.detail ?? "Sign-in failed.") : "Sign-in failed.");
    }
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <div className={styles.brand}>
          <ShieldHalf size={22} />
          <span className={styles.brandName}>ARGUS</span>
        </div>
        <h1 className={styles.title}>Sign in</h1>
        <p className={styles.subtitle}>
          {needsMfa
            ? "Enter the six-digit code from your authenticator app."
            : "Every action you take is recorded against your account."}
        </p>

        {!needsMfa ? (
          <>
            <label className={styles.field}>
              <span className={styles.label}>Username</span>
              <input
                className={styles.input}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Password</span>
              <input
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
          </>
        ) : (
          <label className={styles.field}>
            <span className={styles.label}>Authentication code</span>
            <input
              className={styles.input}
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              autoFocus
              required
            />
          </label>
        )}

        {error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : null}

        <Button type="submit" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : needsMfa ? "Verify" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
