"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell } from "@/components/Shell";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = () =>
    api<Project[]>("/projects")
      .then(setProjects)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load projects"));
  useEffect(() => { load(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await api<Project>("/projects", { method: "POST", body: { name, currency } });
      setName("");
      setProjects((ps) => [p, ...ps]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Your projects</h1>
      <form onSubmit={create} className="mb-6 flex gap-2">
        <input className="flex-1 rounded-md border px-3 py-2" placeholder="e.g. Front elevation — Ahmedabad house" value={name}
          onChange={(e) => setName(e.target.value)} required maxLength={120} />
        <select className="rounded-md border px-2" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          {["INR", "USD", "EUR", "GBP", "AED"].map((c) => <option key={c}>{c}</option>)}
        </select>
        <button disabled={busy} className="rounded-md bg-teal-700 px-4 py-2 text-white disabled:opacity-40">New project</button>
      </form>
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {projects.map((p) => (
          <li key={p.id}>
            <Link href={`/projects/${p.id}`} className="block rounded-lg border bg-white p-4 hover:shadow">
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-zinc-500">{p.status} · {p.currency} · {new Date(p.created_at).toLocaleString()}</div>
            </Link>
          </li>
        ))}
        {projects.length === 0 && <li className="text-sm text-zinc-500">No projects yet — create one above.</li>}
      </ul>
    </Shell>
  );
}
