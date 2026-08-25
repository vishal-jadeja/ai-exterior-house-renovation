"use client";
import { useState } from "react";

/** Before/after comparison: drag the divider, or switch to side-by-side. */
export function CompareSlider({ before, after, width, height }: { before: string; after: string; width: number; height: number }) {
  const [pos, setPos] = useState(50);
  const [mode, setMode] = useState<"slider" | "side">("slider");
  const ratio = `${width} / ${height}`;
  return (
    <div>
      <div className="mb-2 flex items-center gap-3 text-xs">
        <button onClick={() => setMode("slider")} className={`rounded border px-2 py-0.5 ${mode === "slider" ? "bg-zinc-900 text-white" : ""}`}>Slider</button>
        <button onClick={() => setMode("side")} className={`rounded border px-2 py-0.5 ${mode === "side" ? "bg-zinc-900 text-white" : ""}`}>Side by side</button>
      </div>
      {mode === "slider" ? (
        <div className="relative w-full overflow-hidden rounded-md" style={{ aspectRatio: ratio }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={after} alt="Redesigned" className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={before} alt="Original" className="h-full w-full object-cover" />
          </div>
          <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${pos}%` }} />
          <span className="absolute left-2 top-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">Original</span>
          <span className="absolute right-2 top-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">Redesigned</span>
          <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))}
            aria-label="Compare original and redesigned" className="absolute inset-x-0 bottom-2 mx-auto w-11/12 cursor-ew-resize" />
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={before} alt="Original" className="w-full rounded-md" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={after} alt="Redesigned" className="w-full rounded-md" />
        </div>
      )}
    </div>
  );
}
