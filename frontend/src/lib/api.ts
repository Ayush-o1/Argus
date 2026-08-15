const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * API client.
 *
 * There is deliberately no token here. The previous implementation read
 * `NEXT_PUBLIC_ARGUS_API_TOKEN`, which Next.js inlines into the client bundle
 * at build time — so the credential guarding every endpoint was served as
 * static text to every visitor, and the control provided no security property
 * at all (audit B-01).
 *
 * Authentication is now an httpOnly session cookie the browser attaches
 * automatically and JavaScript cannot read. `credentials: "include"` is what
 * makes the browser send it cross-origin, and the CSRF token below is the other
 * half of that tradeoff: because the browser attaches the cookie to *any*
 * request to this origin, including ones initiated by another site, a value
 * only same-origin script can read must be echoed back.
 */

const CSRF_COOKIE = "argus_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export interface Envelope<T> {
  data: T;
  meta?: { total: number; page: number; page_size: number } | null;
  error?: string | null;
}

export class ApiError extends Error {
  status: number;
  /** Present when the backend returned a structured error body. */
  detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const method = (init?.method ?? "GET").toUpperCase();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };

  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    // Without this the browser will not attach the session cookie to a
    // cross-origin request, and every call would be unauthenticated.
    credentials: "include",
  });

  if (!res.ok) {
    // Surface the backend's own message where there is one: "Role 'viewer'
    // lacks permission 'case:create'" is far more useful to an analyst than a
    // bare 403, and it is not sensitive — it describes their own access.
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.error ?? undefined;
    } catch {
      // Non-JSON error body; fall through to the status line.
    }
    throw new ApiError(res.status, detail ?? `${res.status} ${res.statusText} — ${path}`, detail);
  }

  return (await res.json()) as Envelope<T>;
}
