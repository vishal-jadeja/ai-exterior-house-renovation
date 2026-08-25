"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuthStore, type User } from "@/lib/auth-store";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const { setToken, setUser } = useAuthStore();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await api<{ access_token: string }>(`/auth/${mode}`, { method: "POST", body: { email, password } });
      setToken(t.access_token);
      setUser(await api<User>("/auth/me"));
      router.replace("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="mb-6 text-2xl font-semibold">{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <input className="rounded-md border px-3 py-2" type="email" placeholder="Email" value={email} required
          onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        <input className="rounded-md border px-3 py-2" type="password" placeholder="Password (min 8 chars)" value={password}
          required minLength={8} onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "login" ? "current-password" : "new-password"} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={busy} className="rounded-md bg-teal-700 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </form>
      <p className="mt-4 text-sm text-zinc-600">
        {mode === "login" ? (
          <>No account? <Link className="underline" href="/register">Register</Link></>
        ) : (
          <>Have an account? <Link className="underline" href="/login">Sign in</Link></>
        )}
      </p>
    </main>
  );
}
