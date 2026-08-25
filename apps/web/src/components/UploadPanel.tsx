"use client";
import { useCallback, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ImageRec, Quality } from "@/lib/types";

type Props = { projectId: string; onUploaded: (img: ImageRec, q: Quality) => void };

export function UploadPanel({ projectId, onUploaded }: Props) {
  const [busy, setBusy] = useState(false);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);

  const upload = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      setQuality(null);
      const fd = new FormData();
      fd.append("file", file);
      try {
        const res = await api<{ image: ImageRec; quality: Quality }>(`/projects/${projectId}/images`, { method: "POST", body: fd });
        setQuality(res.quality);
        onUploaded(res.image, res.quality);
      } catch (err) {
        if (err instanceof ApiError && err.status === 422 && err.detail && typeof err.detail === "object") {
          const d = (err.detail as { detail?: { quality?: Quality; message?: string } }).detail;
          if (d?.quality) { setQuality(d.quality); setError(d.message ?? "Image not usable"); return; }
        }
        setError(err instanceof ApiError ? err.message : "Upload failed");
      } finally {
        setBusy(false);
      }
    },
    [projectId, onUploaded],
  );

  return (
    <div>
      <label
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center text-sm ${drag ? "border-teal-600 bg-teal-50" : "border-zinc-300 bg-white"}`}
      >
        <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
        <span className="font-medium">{busy ? "Checking image quality…" : "Drop a photo of your house exterior, or click to choose"}</span>
        <span className="mt-1 text-xs text-zinc-500">JPEG/PNG/WebP · up to 10 MB · shoot the full front elevation in daylight</span>
      </label>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {quality && (
        <div className={`mt-3 rounded-md border p-3 text-sm ${quality.usable ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
          <div className="mb-1 font-medium">
            {quality.usable ? "Image accepted" : "Image not usable"} · quality score {quality.score}/100
          </div>
          <ul className="list-disc pl-5 text-zinc-700">{quality.guidance.map((g) => <li key={g}>{g}</li>)}</ul>
          <div className="mt-1 text-xs text-zinc-500">sharpness {quality.blur_score} · brightness {quality.brightness} · contrast {quality.contrast}</div>
        </div>
      )}
    </div>
  );
}
