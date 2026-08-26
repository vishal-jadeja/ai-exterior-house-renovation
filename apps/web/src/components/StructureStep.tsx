"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { EditableRegion } from "@/components/RegionEditor";
import { api, ApiError } from "@/lib/api";
import { waitForJob } from "@/lib/jobs";
import type { ImageRec, Job, Region } from "@/lib/types";

// react-konva touches the canvas/window at module load time, so it can't render on the server.
const RegionEditor = dynamic(() => import("@/components/RegionEditor").then((m) => m.RegionEditor), { ssr: false });

type Props = { projectId: string; image: ImageRec; onRegionsChanged?: (regions: Region[]) => void };

export function StructureStep({ projectId, image, onRegionsChanged }: Props) {
  const [regions, setRegions] = useState<EditableRegion[]>([]);
  const [dirty, setDirty] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const rs = await api<Region[]>(`/projects/${projectId}/regions`);
    setRegions(rs.map((r) => ({ ...r, _key: r.id })));
    setDirty(false);
    onRegionsChanged?.(rs);
  }, [projectId, onRegionsChanged]);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch-then-set
  useEffect(() => { load().catch(() => {}); }, [load]);
  // Abort an in-flight detection poll if the component unmounts (e.g. the photo is replaced).
  useEffect(() => () => abortRef.current?.abort(), []);
  // Warn before leaving the page with unsaved region edits.
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  async function detect() {
    if (
      regions.length > 0 &&
      !window.confirm("Re-running detection replaces model-detected regions — regions you added or edited yourself are kept. Material choices are kept where a region still exists — review the design step afterwards. Continue?")
    ) {
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setMsg(null);
    try {
      const j = await api<Job>(`/projects/${projectId}/segment`, { method: "POST" });
      setJob(j);
      const done = await waitForJob(j.id, setJob, controller.signal);
      if (done.status === "failed") setMsg(`Detection failed: ${done.error ?? "unknown error"}`);
      else {
        const res = done.result as { regions?: number; refined?: boolean; guidance?: string | null } | null;
        setMsg(res?.guidance ?? `Detected ${res?.regions ?? 0} regions${res?.refined ? " (refined with Gemini)" : ""}. Review and adjust them below.`);
      }
      await load();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Detection failed");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
      setJob(null);
    }
  }

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const saved = await api<Region[]>(`/projects/${projectId}/regions`, {
        method: "PUT",
        body: { regions: regions.map((r) => ({ id: r.id, label: r.label, name: r.name, polygon: r.polygon, is_active: true })) },
      });
      setRegions(saved.map((r) => ({ ...r, _key: r.id })));
      setDirty(false);
      onRegionsChanged?.(saved);
      setMsg("Regions saved.");
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">2 · Building structure</h2>
        <div className="ml-auto flex gap-2">
          <button onClick={detect} disabled={busy} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {job ? `Detecting… (${job.status})` : regions.length ? "Re-detect" : "Detect structure"}
          </button>
          <button onClick={save} disabled={busy || !dirty} className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-40">
            Save regions
          </button>
        </div>
      </div>
      {msg && <p className="mb-2 text-sm text-zinc-600">{msg}</p>}
      {regions.length === 0 && !busy && (
        <p className="mb-3 text-sm text-zinc-500">
          Run detection to find walls, windows, doors, railings and pillars. You can then correct anything the model missed.
        </p>
      )}
      {image.url && image.width && image.height && (
        <RegionEditor imageUrl={image.url} imageWidth={image.width} imageHeight={image.height} regions={regions}
          onChange={(rs) => { setRegions(rs); setDirty(true); }} />
      )}
      {regions.length > 0 && (
        <p className="mt-2 text-xs text-zinc-500">
          Tip: add a box for a missed region with “Draw box”, or hide a label from the list to declutter. {dirty && <b>Unsaved changes.</b>}
        </p>
      )}
    </div>
  );
}
