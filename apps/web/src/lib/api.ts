/**
 * Minimal typed API client. Access token lives in memory (zustand) — never in localStorage —
 * and is refreshed via the httpOnly refresh cookie on 401.
 */
import { useAuthStore } from "@/lib/auth-store";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

type Opts = Omit<RequestInit, "body"> & { body?: unknown; raw?: boolean; retry?: boolean };

async function refreshAccessToken(): Promise<string | null> {
  const res = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" });
  if (!res.ok) return null;
  const data = (await res.json()) as { access_token: string };
  useAuthStore.getState().setToken(data.access_token);
  return data.access_token;
}

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const { body, raw, retry = true, headers, ...rest } = opts;
  const token = useAuthStore.getState().token;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    credentials: "include",
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
    const msg =
      typeof detail === "object" && detail && "detail" in detail
        ? typeof (detail as { detail: unknown }).detail === "string"
          ? ((detail as { detail: string }).detail as string)
          : JSON.stringify((detail as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, msg, detail);
  }
  if (raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
