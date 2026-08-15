import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/lib/api";

export type Role = "viewer" | "analyst" | "investigator" | "supervisor" | "administrator" | "auditor";

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  role: Role;
}

export interface Session {
  user: CurrentUser;
  permissions: string[];
}

/** Raised by the login form when the account needs a TOTP code. */
export const MFA_REQUIRED = "mfa_required";

export function useSession() {
  return useQuery<Session | null>({
    queryKey: ["session"],
    queryFn: async () => {
      try {
        return (await apiFetch<Session>("/api/auth/me")).data;
      } catch (err) {
        // Not being logged in is a normal state, not an error to retry or
        // surface — the app renders the login screen instead.
        if (err instanceof ApiError && err.isAuthError) return null;
        throw err;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: { username: string; password: string; mfa_code?: string }) =>
      (await apiFetch<Session>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(credentials),
      })).data,
    onSuccess: (session) => {
      queryClient.setQueryData(["session"], session);
      // Every cached response was fetched as whoever was logged in before —
      // possibly nobody. Clearing prevents one user briefly seeing another's
      // data from cache.
      queryClient.invalidateQueries();
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiFetch<{ logged_out: boolean }>("/api/auth/logout", { method: "POST" })).data,
    onSuccess: () => {
      queryClient.setQueryData(["session"], null);
      queryClient.clear();
    },
  });
}

/**
 * Whether the current user holds a permission.
 *
 * Used to hide surfaces the user cannot use. This is a usability affordance and
 * never a security control — every permission is enforced again on the server,
 * because a hidden button is not a boundary.
 */
export function useHasPermission(permission: string): boolean {
  const { data: session } = useSession();
  return session?.permissions.includes(permission) ?? false;
}
