"use client";
import { msgClass } from "@/lib/format";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { waitForJob } from "@/lib/jobs";
import type { Design, ReportRec } from "@/lib/types";

/** Spec 5.8 — downloadable PDF report usable as a discussion document with contractors. */
export function ReportStep({ design }: { design: Design | null }) {
  const [reports, setReports] = useState<ReportRec[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!design) { setReports([]); return; }
    const rs = await api<ReportRec[]>(`/designs/${design.id}/reports`);
    setReports(rs);
    return rs;
  }, [design]);

  // Load reports for the current design, then resume polling one left in-flight by a
  // previous page load (queued/running with a job_id).
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    (async () => {
      const rs = await load().catch(() => null);
      const pending = rs?.find((r) => (r.status === "queued" || r.status === "running") && r.job_id);
      if (!pending?.job_id) return;
      setBusy(true);
      setMsg("Building PDF…");
      try {
        const j = await waitForJob(pending.job_id, undefined, controller.signal);
        setMsg(j.status === "failed" ? `Report failed: ${j.error ?? "unknown error"}` : null);
        await load();
      } catch {
        // aborted (unmount / design change) or a poll request failed — nothing to surface
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => { controller.abort(); abortRef.current?.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resume-on-mount is keyed on design only
  }, [design?.id]);

  async function generate() {
    if (!design) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setMsg("Building PDF…");
    try {
      const r = await api<ReportRec>(`/designs/${design.id}/report`, { method: "POST" });
      if (r.job_id) {
        const j = await waitForJob(r.job_id, undefined, controller.signal);
        setMsg(j.status === "failed" ? `Report failed: ${j.error ?? "unknown error"}` : null);
      }
      await load();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Report failed");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const latest = reports.find((r) => r.status === "done") ?? null;
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">6 · Report</h2>
        <span className="text-xs text-zinc-500">Original + redesigned images, materials, quantities, cost breakdown and assumptions.</span>
        <div className="ml-auto flex gap-2">
          {latest?.url && (
            <a href={latest.url} className="rounded-md border px-3 py-1.5 text-sm" target="_blank" rel="noreferrer">Download PDF</a>
          )}
          <button onClick={generate} disabled={busy || !design} className="rounded-md bg-teal-700 px-3 py-1.5 text-sm text-white disabled:opacity-40">
            {busy ? "Building…" : latest ? "Regenerate report" : "Generate report"}
          </button>
        </div>
      </div>
      {msg && <p className={`text-sm ${msgClass(msg)}`}>{msg}</p>}
      {latest && <p className="text-xs text-zinc-500">Latest report generated {new Date(latest.created_at).toLocaleString()}. Links expire after 15 minutes; regenerate or reload to get a fresh one.</p>}
    </div>
  );
}
