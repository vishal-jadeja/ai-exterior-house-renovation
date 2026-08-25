"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Image as KImage, Line, Circle, Rect, Text, Group } from "react-konva";
import type Konva from "konva";
import { LABELS, LABEL_COLORS, LABEL_NAMES } from "@/lib/labels";
import type { Region, RegionLabel } from "@/lib/types";

export type EditableRegion = Omit<Region, "id"> & { id: string | null; _key: string };

type Props = {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  regions: EditableRegion[];
  onChange: (regions: EditableRegion[]) => void;
  readOnly?: boolean;
};

let keySeq = 0;
export const newKey = () => `new-${++keySeq}-${Math.random().toString(36).slice(2, 7)}`;

function useImage(url: string) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    const el = new window.Image();
    el.crossOrigin = "anonymous";
    el.onload = () => setImg(el);
    el.src = url;
  }, [url]);
  return img;
}

/**
 * Canvas overlay for reviewing/correcting detected building regions (spec 5.2).
 * Vertices of the selected region are draggable; regions can be relabelled, deleted, or drawn as rectangles.
 */
export function RegionEditor({ imageUrl, imageWidth, imageHeight, regions, onChange, readOnly }: Props) {
  const img = useImage(imageUrl);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapW, setWrapW] = useState(800);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [tool, setTool] = useState<"select" | "rect">("select");
  const [newLabel, setNewLabel] = useState<RegionLabel>("wall");
  const [hidden, setHidden] = useState<Set<RegionLabel>>(new Set());

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((e) => setWrapW(e[0].contentRect.width));
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const scale = Math.min(1, wrapW / imageWidth);
  const stageW = imageWidth * scale;
  const stageH = imageHeight * scale;
  const sel = useMemo(() => regions.find((r) => r._key === selected) ?? null, [regions, selected]);

  const update = (key: string, patch: Partial<EditableRegion>) =>
    onChange(regions.map((r) => (r._key === key ? { ...r, ...patch } : r)));
  const remove = (key: string) => {
    onChange(regions.filter((r) => r._key !== key));
    setSelected(null);
  };

  const toImg = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    const p = e.target.getStage()?.getPointerPosition();
    return p ? { x: p.x / scale, y: p.y / scale } : null;
  };

  const onDown = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (readOnly) return;
    if (tool === "rect") {
      const p = toImg(e);
      if (p) { setDrawing(p); setDraft({ x: p.x, y: p.y, w: 0, h: 0 }); }
    } else if (e.target === e.target.getStage() || e.target.name() === "bg") {
      setSelected(null);
    }
  };
  const onMove = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (!drawing) return;
    const p = toImg(e);
    if (p) setDraft({ x: Math.min(p.x, drawing.x), y: Math.min(p.y, drawing.y), w: Math.abs(p.x - drawing.x), h: Math.abs(p.y - drawing.y) });
  };
  const onUp = () => {
    if (drawing && draft && draft.w > 8 && draft.h > 8) {
      const { x, y, w, h } = draft;
      const count = regions.filter((r) => r.label === newLabel).length + 1;
      const r: EditableRegion = {
        id: null, _key: newKey(), label: newLabel, name: `${LABEL_NAMES[newLabel]} ${count}`,
        polygon: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], pixel_area: w * h, bbox: [x, y, w, h],
        confidence: 1, source: "user", version: 1, is_active: true, image_id: regions[0]?.image_id ?? "",
      };
      onChange([...regions, r]);
      setSelected(r._key);
      setTool("select");
    }
    setDrawing(null);
    setDraft(null);
  };

  const visible = regions.filter((r) => !hidden.has(r.label));

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
      <div ref={wrapRef} className="overflow-hidden rounded-md border bg-zinc-100">
        <Stage width={stageW} height={stageH} scaleX={scale} scaleY={scale}
          onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onTouchStart={onDown} onTouchMove={onMove} onTouchEnd={onUp}
          style={{ cursor: tool === "rect" ? "crosshair" : "default" }}>
          <Layer>
            {img && <KImage image={img} width={imageWidth} height={imageHeight} name="bg" />}
            {visible.map((r) => {
              const color = LABEL_COLORS[r.label];
              const isSel = r._key === selected;
              return (
                <Group key={r._key}>
                  <Line points={r.polygon.flat()} closed fill={color + (isSel ? "66" : "33")} stroke={color}
                    strokeWidth={(isSel ? 3 : 1.5) / scale} onClick={() => setSelected(r._key)} onTap={() => setSelected(r._key)} />
                  <Text x={r.bbox[0] + 4 / scale} y={r.bbox[1] + 4 / scale} text={r.name} fontSize={13 / scale} fill="#fff"
                    shadowColor="#000" shadowBlur={3} listening={false} />
                  {isSel && !readOnly && r.polygon.map((p, i) => (
                    <Circle key={i} x={p[0]} y={p[1]} radius={6 / scale} fill="#fff" stroke={color} strokeWidth={2 / scale} draggable
                      onDragMove={(e) => {
                        const poly = r.polygon.map((q, j) => (j === i ? [e.target.x(), e.target.y()] : q));
                        const xs = poly.map((q) => q[0]), ys = poly.map((q) => q[1]);
                        update(r._key, { polygon: poly, bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)] });
                      }} />
                  ))}
                </Group>
              );
            })}
            {draft && <Rect x={draft.x} y={draft.y} width={draft.w} height={draft.h} stroke={LABEL_COLORS[newLabel]} dash={[6 / scale, 4 / scale]} strokeWidth={2 / scale} />}
          </Layer>
        </Stage>
      </div>

      <aside className="flex flex-col gap-3 text-sm">
        {!readOnly && (
          <div className="rounded-md border bg-white p-3">
            <div className="mb-2 font-medium">Tools</div>
            <div className="flex gap-2">
              <button onClick={() => setTool("select")} className={`rounded border px-2 py-1 ${tool === "select" ? "bg-zinc-900 text-white" : ""}`}>Select</button>
              <button onClick={() => setTool("rect")} className={`rounded border px-2 py-1 ${tool === "rect" ? "bg-zinc-900 text-white" : ""}`}>Draw box</button>
              <select className="flex-1 rounded border px-1" value={newLabel} onChange={(e) => setNewLabel(e.target.value as RegionLabel)}>
                {LABELS.map((l) => <option key={l} value={l}>{LABEL_NAMES[l]}</option>)}
              </select>
            </div>
            <p className="mt-2 text-xs text-zinc-500">Click a region to select it, then drag its corner handles. Use “Draw box” to add a missed area.</p>
          </div>
        )}
        {sel && !readOnly && (
          <div className="rounded-md border bg-white p-3">
            <div className="mb-2 font-medium">Selected</div>
            <input className="mb-2 w-full rounded border px-2 py-1" value={sel.name} maxLength={64} onChange={(e) => update(sel._key, { name: e.target.value })} />
            <select className="mb-2 w-full rounded border px-2 py-1" value={sel.label} onChange={(e) => update(sel._key, { label: e.target.value as RegionLabel })}>
              {LABELS.map((l) => <option key={l} value={l}>{LABEL_NAMES[l]}</option>)}
            </select>
            <div className="mb-2 text-xs text-zinc-500">source {sel.source} · confidence {Math.round(sel.confidence * 100)}%</div>
            <button onClick={() => remove(sel._key)} className="w-full rounded border border-red-300 px-2 py-1 text-red-700 hover:bg-red-50">Delete region</button>
          </div>
        )}
        <div className="rounded-md border bg-white p-3">
          <div className="mb-2 font-medium">Regions ({regions.length})</div>
          <ul className="max-h-72 space-y-1 overflow-auto">
            {LABELS.filter((l) => regions.some((r) => r.label === l)).map((l) => (
              <li key={l}>
                <button onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(l)) n.delete(l); else n.add(l); return n; })}
                  className={`flex w-full items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-zinc-50 ${hidden.has(l) ? "opacity-40" : ""}`}>
                  <span className="inline-block h-3 w-3 rounded-sm" style={{ background: LABEL_COLORS[l] }} />
                  {LABEL_NAMES[l]} <span className="ml-auto text-xs text-zinc-500">{regions.filter((r) => r.label === l).length}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
