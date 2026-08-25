"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export function Shell({ children }: { children: React.ReactNode }) {
  const { user, clear } = useAuthStore();
  const router = useRouter();
  async function logout() {
    try { await api("/auth/logout", { method: "POST" }); } catch {}
    clear();
    router.replace("/login");
  }
  return (
    <div className="min-h-screen">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link href="/projects" className="font-semibold text-teal-800">RenovAI</Link>
          <div className="flex items-center gap-4 text-sm text-zinc-600">
            {user?.email}
            <button onClick={logout} className="rounded border px-3 py-1 hover:bg-zinc-50">Sign out</button>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-6 py-6">{children}</div>
    </div>
  );
}
