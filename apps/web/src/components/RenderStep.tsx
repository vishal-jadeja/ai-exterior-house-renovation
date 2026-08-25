"use client";
import { useCallback, useEffect, useState } from "react";
import { CompareSlider } from "@/components/CompareSlider";
import { api, ApiError } from "@/lib/api";
import { waitForJob } from "@/lib/jobs";
import type { Design, ImageRec, RenderRec } from "@/lib/types";

type Props = { design: Design | null; image: ImageRec };

const PROVIDER_LABEL: Record<string, string> = { local: "Local compositor", cloudflare: "Cloudflare Workers AI (SD inpainting)", fal: "fal.ai FLUX Fill" };

/** Spec 5.4 — redesigned visualisation of the user's own house with before/after comparison. */
export function RenderStep({ design, image }: Props) {
  const [renders, setRenders] = useState<RenderRec[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!design) { setRenders([]); return; }
    const rs = await api<RenderRec[]>(`/designs/${design.id}/renders`);
    setRenders(rs);
    setSelected((s) => (s && rs.some((r) => r.id === s) ? s : rs.find((r) => r.status === "done")?.id ?? null));
  }, [design]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch-then-set
  useEffect(() => { load().catch(() => {}); }, [load]);

  async function generate() {
    if (!design) return;
    setBusy(true);
    setMsg("Rendering… the local compositor takes a few seconds; hosted AI providers up to a minute.");
    try {
      const r = await api<RenderRec>(`/designs/${design.id}/render`, { method: "POST" });
      if (r.job_id) {
        const j = await waitForJob(r.job_id);
        if (j.status === "failed") setMsg(`Render failed: ${j.error ?? "unknown error"}`);
        else setMsg(null);
      }
      await load();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Render failed");
    } finally {
      setBusy(false);
    }
  }

  const current = renders.find((r) => r.id === selected) ?? null;

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">4 · Redesign preview</h2>
        <span className="text-xs text-zinc-500">{design ? `design: ${design.name}` : "no design selected"}</span>
        <button onClick={generate} disabled={busy || !design || design.assignments.length === 0}
          className="ml-auto rounded-md bg-teal-700 px-3 py-1.5 text-sm text-white disabled:opacity-40">
          {busy ? "Rendering…" : "Generate redesign"}
        </button>
      </div>
      {msg && <p className="mb-2 text-sm text-zinc-600">{msg}</p>}
      {design && design.assignments.length === 0 && <p className="text-sm text-zinc-500">Assign and save at least one material in the design above.</p>}
      {current?.url && image.url && image.width && image.height && (
        <>
          <CompareSlider before={image.url} after={current.url} width={image.width} height={image.height} />
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-600">
            <span className="rounded-full bg-zinc-100 px-2 py-0.5">Provider: {PROVIDER_LABEL[current.provider_used ?? ""] ?? current.provider_used}</span>
            {current.provider_log.filter((l) => l.status !== "ok").map((l, i) => (
              <span key={i} className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800" title={l.reason}>{l.provider}: {l.status}</span>
            ))}
            {renders.length > 1 && (
              <select className="ml-auto rounded border px-1 py-0.5" value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
                {renders.filter((r) => r.status === "done").map((r) => (
                  <option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleTimeString()} · {r.provider_used}</option>
                ))}
              </select>
            )}
          </div>
        </>
      )}
    </div>
  );
}
