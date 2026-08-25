"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { LABEL_COLORS, LABEL_NAMES } from "@/lib/labels";
import type { Assignment, Design, Material, Region, RegionLabel } from "@/lib/types";

type Props = { projectId: string; regions: Region[]; onActiveDesign?: (d: Design | null) => void };

/** Spec 5.3 — material catalog, per-region assignment, multiple design variants. */
export function DesignStep({ projectId, regions, onActiveDesign }: Props) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, Assignment>>({});
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [ms, ds] = await Promise.all([api<Material[]>("/materials"), api<Design[]>(`/projects/${projectId}/designs`)]);
    setMaterials(ms);
    setDesigns(ds);
    const active = ds.find((d) => d.is_active) ?? ds[0] ?? null;
    setCurrent((c) => c && ds.some((d) => d.id === c) ? c : active?.id ?? null);
  }, [projectId]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch-then-set
  useEffect(() => { load().catch(() => {}); }, [load]);

  const design = useMemo(() => designs.find((d) => d.id === current) ?? null, [designs, current]);
  useEffect(() => { onActiveDesign?.(design); }, [design, onActiveDesign]);
  useEffect(() => {
    const map: Record<string, Assignment> = {};
    design?.assignments.forEach((a) => { map[a.region_id] = a; });
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset draft when switching designs
    setDraft(map);
    setDirty(false);
  }, [design]);

  const byLabel = (label: RegionLabel) => materials.filter((m) => m.applicable_labels.includes(label));
  // window/door are informational only; roof_edge is hidden only while no material applies to it.
  const surfaces = regions.filter(
    (r) => r.label !== "window" && r.label !== "door" && (r.label !== "roof_edge" || byLabel("roof_edge").length > 0),
  );

  /** Wraps a design action so any ApiError surfaces in `msg` instead of failing silently. */
  function guard(fn: () => Promise<void>) {
    return async () => {
      setBusy(true);
      setMsg(null);
      try {
        await fn();
      } catch (err) {
        setMsg(err instanceof ApiError ? err.message : "Action failed");
      } finally {
        setBusy(false);
      }
    };
  }

  const createDesign = guard(async () => {
    const name = `Design ${designs.length + 1}`;
    const d = await api<Design>(`/projects/${projectId}/designs`, { method: "POST", body: { name } });
    await load();
    setCurrent(d.id);
  });
  const clone = guard(async () => {
    if (!design) return;
    const d = await api<Design>(`/designs/${design.id}/clone`, { method: "POST" });
    await load();
    setCurrent(d.id);
  });
  const activate = guard(async () => {
    if (!design) return;
    await api(`/designs/${design.id}/activate`, { method: "POST" });
    await load();
  });
  const rename = guard(async () => {
    if (!design) return;
    const name = window.prompt("Design name", design.name);
    if (!name) return;
    await api(`/designs/${design.id}`, { method: "PATCH", body: { name } });
    await load();
  });
  const remove = guard(async () => {
    if (!design) return;
    if (!window.confirm(`Delete "${design.name}"? This cannot be undone.`)) return;
    await api(`/designs/${design.id}`, { method: "DELETE" });
    setCurrent(null);
    await load();
  });
  async function save() {
    if (!design) return;
    setBusy(true);
    setMsg(null);
    try {
      const assignments = Object.values(draft).map((a) => ({ region_id: a.region_id, material_id: a.material_id, color_hex: a.color_hex ?? null }));
      await api(`/designs/${design.id}/assignments`, { method: "PUT", body: { assignments } });
      await load();
      setMsg("Design saved.");
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  function setMaterial(regionId: string, materialId: string) {
    setDraft((d) => {
      const n = { ...d };
      if (!materialId) delete n[regionId];
      else {
        const m = materials.find((x) => x.id === materialId);
        n[regionId] = { region_id: regionId, material_id: materialId, color_hex: m?.color_hex ?? null };
      }
      return n;
    });
    setDirty(true);
  }
  function applyToAll(label: RegionLabel, materialId: string) {
    surfaces.filter((r) => r.label === label).forEach((r) => setMaterial(r.id, materialId));
  }

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">3 · Materials &amp; design variants</h2>
        <div className="ml-auto flex flex-wrap gap-2 text-sm">
          <button onClick={createDesign} disabled={busy} className="rounded-md border px-3 py-1.5 disabled:opacity-40">New design</button>
          {design && (<>
            <button onClick={clone} disabled={busy} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Duplicate</button>
            <button onClick={rename} disabled={busy} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Rename</button>
            <button onClick={activate} disabled={busy || design.is_active} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Set active</button>
            <button onClick={remove} disabled={busy} className="rounded-md border border-red-300 px-3 py-1.5 text-red-700 disabled:opacity-40">Delete</button>
            <button onClick={save} disabled={busy || !dirty} className="rounded-md bg-teal-700 px-3 py-1.5 text-white disabled:opacity-40">Save design</button>
          </>)}
        </div>
      </div>
      {designs.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1 border-b">
          {designs.map((d) => (
            <button key={d.id} onClick={() => setCurrent(d.id)}
              className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${d.id === current ? "border-teal-700 font-medium" : "border-transparent text-zinc-500"}`}>
              {d.name}{d.is_active && <span className="ml-1 rounded bg-teal-100 px-1 text-[10px] text-teal-800">active</span>}
            </button>
          ))}
        </div>
      )}
      {msg && <p className="mb-2 text-sm text-zinc-600">{msg}</p>}
      {!design && <p className="text-sm text-zinc-500">Create a design to start assigning materials to surfaces.</p>}
      {design && surfaces.length === 0 && <p className="text-sm text-zinc-500">No paintable surfaces yet — detect the building structure first.</p>}
      {design && surfaces.length > 0 && (
        <div className="grid gap-4 md:grid-cols-[1fr_300px]">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-zinc-500"><th className="py-1">Surface</th><th>Material</th><th className="w-20">Colour</th></tr></thead>
            <tbody>
              {surfaces.map((r) => {
                const a = draft[r.id];
                const m = materials.find((x) => x.id === a?.material_id);
                return (
                  <tr key={r.id} className="border-t">
                    <td className="py-1.5">
                      <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LABEL_COLORS[r.label] }} />
                      {r.name}
                      <button onClick={() => a && applyToAll(r.label, a.material_id)} title={`Apply to all ${LABEL_NAMES[r.label]}s`}
                        className="ml-2 text-[11px] text-teal-700 underline disabled:hidden" disabled={!a}>all {LABEL_NAMES[r.label].toLowerCase()}s</button>
                    </td>
                    <td>
                      <select className="w-full rounded border px-1 py-1" value={a?.material_id ?? ""} onChange={(e) => setMaterial(r.id, e.target.value)}>
                        <option value="">— keep as is —</option>
                        {byLabel(r.label).map((mm) => <option key={mm.id} value={mm.id}>{mm.name}</option>)}
                      </select>
                    </td>
                    <td>
                      {m?.category === "paint" || m?.category === "texture" ? (
                        <input type="color" value={a?.color_hex ?? "#e8e2d4"} onChange={(e) => { setDraft((d) => ({ ...d, [r.id]: { ...d[r.id], color_hex: e.target.value } })); setDirty(true); }} />
                      ) : m?.texture_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={m.texture_url} alt="" className="h-7 w-14 rounded object-cover" />
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <aside className="rounded-md border bg-zinc-50 p-3 text-xs">
            <div className="mb-2 font-medium">Catalog</div>
            <ul className="max-h-80 space-y-2 overflow-auto">
              {materials.map((m) => (
                <li key={m.id} className="flex gap-2">
                  {m.texture_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.texture_url} alt="" className="h-9 w-9 flex-none rounded object-cover" />
                  )}
                  <div>
                    <div className="font-medium">{m.name}</div>
                    <div className="text-zinc-500">{m.currency} {m.default_material_rate}/{m.quantity_unit} · labour {m.default_labor_rate}/{m.unit} · {m.durability_years}y · {m.maintenance} upkeep</div>
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}
    </div>
  );
}
