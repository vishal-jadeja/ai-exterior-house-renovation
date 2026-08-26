/**
 * Minimal typed API client. Access token lives in memory (zustand) — never in localStorage —
 * and is refreshed via the httpOnly refresh cookie on 401.
 */
import { useAuthStore } from "@/lib/auth-store";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

type Opts = Omit<RequestInit, "body"> & { body?: unknown; retry?: boolean; timeoutMs?: number };

// Concurrent 401s share one refresh instead of each firing their own request against the
// single-use refresh cookie (the second would just fail and log the user out).
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token: string };
      useAuthStore.getState().setToken(data.access_token);
      return data.access_token;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

function pydanticDetailMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const items = detail as { loc?: unknown[]; msg?: string }[];
  if (!items.every((d) => Array.isArray(d.loc) && typeof d.msg === "string")) return null;
  // loc[0] is always "body"/"query"/etc — drop it, keep the field path.
  return items.map((d) => `${(d.loc as unknown[]).slice(1).join(".")}: ${d.msg}`).join("; ");
}

function timeoutSignal(caller?: AbortSignal | null, ms: number = REQUEST_TIMEOUT_MS): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return caller ? AbortSignal.any([caller, timeout]) : timeout;
}

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const { body, retry = true, headers, signal, timeoutMs, ...rest } = opts;
  const token = useAuthStore.getState().token;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    credentials: "include",
    signal: timeoutSignal(signal, timeoutMs),
    headers: {
      ...(isForm ? {} : body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    const fresh = await refreshAccessToken();
    if (fresh) return api<T>(path, { ...opts, retry: false });
    useAuthStore.getState().clear();
  }
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {}
    const inner = typeof detail === "object" && detail && "detail" in detail ? (detail as { detail: unknown }).detail : undefined;
    const msg =
      typeof inner === "string" ? inner : (inner !== undefined ? pydanticDetailMessage(inner) ?? JSON.stringify(inner) : res.statusText);
    throw new ApiError(res.status, msg, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
