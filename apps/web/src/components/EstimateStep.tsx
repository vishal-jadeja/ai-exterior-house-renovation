"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, num } from "@/lib/format";
import { LABEL_NAMES } from "@/lib/labels";
import type { Design, Estimate, Project, Rate } from "@/lib/types";

type Props = { project: Project; design: Design | null; onProjectChanged: (p: Project) => void };

const CONF: Record<string, string> = { high: "bg-emerald-100 text-emerald-800", medium: "bg-amber-100 text-amber-800", low: "bg-red-100 text-red-800" };
const CONF_FALLBACK = "bg-zinc-100 text-zinc-700";
const METHOD: Record<string, string> = {
  user_measurement: "your measurements", door_reference: "door height reference (7 ft)",
  window_reference: "window height reference (4 ft)", floor_count: "floor count × 10 ft", default_assumption: "default 30 ft facade assumption",
};

/** Spec 5.5–5.7: measurements → areas → quantities → itemised cost with editable rates. */
export function EstimateStep({ project, design, onProjectChanged }: Props) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [rates, setRates] = useState<Rate[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [width, setWidth] = useState(project.facade_width_ft?.toString() ?? "");
  const [height, setHeight] = useState(project.facade_height_ft?.toString() ?? "");
  const [floors, setFloors] = useState(project.floors?.toString() ?? "");
  const [edits, setEdits] = useState<Record<string, { material_rate: string; labor_rate: string }>>({});

  const load = useCallback(async () => {
    const rc = await api<{ rates: Rate[] }>(`/projects/${project.id}/rate-card`);
    setRates(rc.rates);
    if (design) {
      try { setEst(await api<Estimate>(`/designs/${design.id}/estimate`)); } catch { setEst(null); }
    } else setEst(null);
  }, [project.id, design]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch-then-set
  useEffect(() => { load().catch(() => {}); }, [load]);

  async function run(after?: () => Promise<void>) {
    if (!design) return;
    setBusy(true);
    setMsg(null);
    try {
      if (after) await after();
      setEst(await api<Estimate>(`/designs/${design.id}/estimate`, { method: "POST" }));
      await load();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Estimation failed");
    } finally {
      setBusy(false);
    }
  }

  const saveMeasurements = () => {
    const w = width ? Number(width) : null;
    const h = height ? Number(height) : null;
    if ((w !== null && w < 6) || (h !== null && h < 6)) {
      setMsg("Facade width/height must be at least 6 ft — leave a field blank to let the system infer it instead.");
      return;
    }
    return run(async () => {
      const p = await api<Project>(`/projects/${project.id}/measurements`, {
        method: "PATCH",
        body: { facade_width_ft: w, facade_height_ft: h, floors: floors ? Number(floors) : null },
      });
      onProjectChanged(p);
    });
  };

  const applyRates = () => run(async () => {
    const items = Object.entries(edits).map(([material_id, v]) => ({
      material_id,
      material_rate: Number(v.material_rate),
      labor_rate: Number(v.labor_rate),
    }));
    if (items.length) await api(`/projects/${project.id}/rate-card`, { method: "PUT", body: { rates: items } });
    setEdits({});
  });

  const resetRates = () => run(async () => { await api(`/projects/${project.id}/rate-card`, { method: "DELETE" }); setEdits({}); });

  const p = est?.payload;
  const cur = est?.currency ?? project.currency;
  const usedMaterials = new Set(p?.lines.map((l) => l.material_id));

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">5 · Quantities &amp; cost estimate</h2>
        <button onClick={() => run()} disabled={busy || !design || design.assignments.length === 0}
          className="ml-auto rounded-md bg-teal-700 px-3 py-1.5 text-sm text-white disabled:opacity-40">
          {busy ? "Calculating…" : est ? "Recalculate" : "Calculate estimate"}
        </button>
      </div>
      {msg && <p className="mb-2 text-sm text-red-600">{msg}</p>}
      {est?.stale && (
        <p className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm text-amber-800">
          Rates/regions changed — recalculate to see updated numbers.
        </p>
      )}

      <details className="mb-3 rounded-md border bg-zinc-50 p-3 text-sm" open={!project.facade_width_ft}>
        <summary className="cursor-pointer font-medium">Optional measurements (improves accuracy)</summary>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="text-xs">Facade width (ft)<input className="block w-28 rounded border px-2 py-1" type="number" min={6} value={width} onChange={(e) => setWidth(e.target.value)} placeholder="e.g. 30" /></label>
          <label className="text-xs">Facade height (ft)<input className="block w-28 rounded border px-2 py-1" type="number" min={6} value={height} onChange={(e) => setHeight(e.target.value)} placeholder="e.g. 20" /></label>
          <label className="text-xs">Floors<input className="block w-20 rounded border px-2 py-1" type="number" min={1} max={6} value={floors} onChange={(e) => setFloors(e.target.value)} /></label>
          <button onClick={saveMeasurements} disabled={busy || !design} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Save &amp; recalculate</button>
          <span className="text-xs text-zinc-500">Measure the front wall with a tape if you can; otherwise the system infers scale from the door/windows.</span>
        </div>
      </details>

      {p && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full px-2 py-0.5 ${CONF[p.scale.confidence] ?? CONF_FALLBACK}`}>scale confidence: {p.scale.confidence}</span>
            <span className="text-zinc-600">Scale from {METHOD[p.scale.method] ?? p.scale.method} · 1 px ≈ {num(p.scale.ft_per_px * 12, 2)} in</span>
          </div>

          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Stat label="Material" value={money(p.material_total, cur)} />
            <Stat label="Labour" value={money(p.labor_total, cur)} />
            <Stat label="Grand total" value={money(p.grand_total, cur)} strong />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-zinc-500">
                <th className="py-1">Surface</th><th>Material</th><th className="text-right">Area / length</th><th className="text-right">Quantity</th>
                <th className="text-right">Material rate</th><th className="text-right">Labour rate</th><th className="text-right">Material</th><th className="text-right">Labour</th><th className="text-right">Total</th>
              </tr></thead>
              <tbody>
                {p.lines.map((l) => {
                  const e = edits[l.material_id] ?? { material_rate: String(l.material_rate), labor_rate: String(l.labor_rate) };
                  const set = (k: "material_rate" | "labor_rate", v: string) => setEdits((x) => ({ ...x, [l.material_id]: { ...e, [k]: v } }));
                  return (
                    <tr key={l.region_id} className="border-t align-top">
                      <td className="py-1.5">{l.region_name}<div className="text-[11px] text-zinc-500">{LABEL_NAMES[l.label]}</div></td>
                      <td>{l.material_name}<div className="text-[11px] text-zinc-500">{l.notes.join(" · ")}</div></td>
                      <td className="text-right">{num(l.surface)} {l.surface_unit}</td>
                      <td className="text-right">{num(l.quantity, 2)} {l.quantity_unit}{l.packs != null && <div className="text-[11px] text-zinc-500">{l.packs} {l.pack_label}</div>}</td>
                      <td className="text-right"><input type="number" className="w-24 rounded border px-1 py-0.5 text-right" value={e.material_rate} onChange={(ev) => set("material_rate", ev.target.value)} /><div className="text-[11px] text-zinc-500">per {l.quantity_unit}</div></td>
                      <td className="text-right"><input type="number" className="w-20 rounded border px-1 py-0.5 text-right" value={e.labor_rate} onChange={(ev) => set("labor_rate", ev.target.value)} /><div className="text-[11px] text-zinc-500">per {l.surface_unit}</div></td>
                      <td className="text-right">{money(l.material_cost, cur)}</td>
                      <td className="text-right">{money(l.labor_cost, cur)}</td>
                      <td className="text-right font-medium">{money(l.total, cur)}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                {p.categories.map((c) => (
                  <tr key={c.category} className="border-t text-xs text-zinc-600">
                    <td colSpan={6} className="py-1 capitalize">{c.category} subtotal</td>
                    <td className="text-right">{money(c.material_cost, cur)}</td><td className="text-right">{money(c.labor_cost, cur)}</td><td className="text-right">{money(c.total, cur)}</td>
                  </tr>
                ))}
                <tr className="border-t font-semibold"><td colSpan={8} className="py-2">Grand total ({cur})</td><td className="text-right">{money(p.grand_total, cur)}</td></tr>
              </tfoot>
            </table>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <button onClick={applyRates} disabled={busy || Object.keys(edits).length === 0} className="rounded-md bg-zinc-900 px-3 py-1.5 text-white disabled:opacity-40">Apply rates &amp; recalculate</button>
            <button onClick={resetRates} disabled={busy || !rates.some((r) => r.overridden && usedMaterials.has(r.material_id))} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Reset to catalog rates</button>
            <span className="text-xs text-zinc-500">Estimate v{est?.version} · rates you change are saved for this project only.</span>
          </div>

          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-zinc-700">How these numbers were derived ({p.surfaces.length} surfaces measured)</summary>
            <ul className="mt-2 list-disc pl-5 text-xs text-zinc-600">{p.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            <table className="mt-2 w-full text-xs">
              <thead><tr className="text-left text-zinc-500"><th>Surface</th><th className="text-right">Area (sqft)</th><th className="text-right">Length (ft)</th><th>Method</th><th>Notes</th></tr></thead>
              <tbody>{p.surfaces.map((s) => (
                <tr key={s.region_id} className="border-t"><td className="py-0.5">{s.name}</td><td className="text-right">{num(s.area_sqft)}</td><td className="text-right">{s.length_ft ?? "—"}</td><td>{s.method}</td><td className="text-zinc-500">{s.notes.join("; ")}</td></tr>
              ))}</tbody>
            </table>
          </details>
        </>
      )}
      {!p && design && <p className="text-sm text-zinc-500">Assign materials, then calculate to see areas, quantities and an itemised cost.</p>}
    </div>
  );
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`rounded-md border p-3 ${strong ? "border-teal-300 bg-teal-50" : "bg-zinc-50"}`}>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`text-lg ${strong ? "font-semibold text-teal-900" : "font-medium"}`}>{value}</div>
    </div>
  );
}
