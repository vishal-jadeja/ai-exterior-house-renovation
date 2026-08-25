"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore, type User } from "@/lib/auth-store";

const PUBLIC = new Set(["/", "/login", "/register"]);

/** Silently restores a session from the refresh cookie on first load, and guards private routes. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { hydrated, setHydrated, setToken, setUser, user } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (hydrated) return;
    (async () => {
      try {
        const t = await api<{ access_token: string }>("/auth/refresh", { method: "POST", retry: false });
        setToken(t.access_token);
        setUser(await api<User>("/auth/me"));
      } catch {
        /* not logged in */
      } finally {
        setHydrated();
      }
    })();
  }, [hydrated, setHydrated, setToken, setUser]);

  useEffect(() => {
    if (hydrated && !user && !PUBLIC.has(pathname)) router.replace("/login");
  }, [hydrated, user, pathname, router]);

  if (!hydrated) return <div className="p-8 text-sm text-zinc-500">Loading…</div>;
  return <>{children}</>;
}
