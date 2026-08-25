export type Project = {
  id: string; name: string; currency: string; unit_system: string; status: string;
  scale_ft_per_px: number | null; scale_method: string | null; scale_confidence: string | null;
  facade_width_ft: number | null; facade_height_ft: number | null; floors: number | null;
  created_at: string; updated_at: string;
};
export type Quality = { usable: boolean; score: number; blur_score: number; brightness: number; contrast: number; guidance: string[] };
export type ImageRec = { id: string; kind: string; width: number | null; height: number | null; quality_score: number | null; meta: Record<string, unknown>; url: string | null; created_at: string };
export type RegionLabel = "wall" | "window" | "door" | "balcony" | "railing" | "pillar" | "parapet" | "gate" | "roof_edge";
export type Region = { id: string; image_id: string; label: RegionLabel; name: string; polygon: number[][]; pixel_area: number; bbox: number[]; confidence: number; source: string; version: number; is_active: boolean };
export type Material = { id: string; category: string; name: string; description: string; unit: string; quantity_unit: string; coverage: number | null; coats: number; piece_area_sqft: number | null; pieces_per_box: number | null; wastage_pct: number; default_material_rate: number; default_labor_rate: number; currency: string; texture_key: string | null; texture_url?: string | null; color_hex: string | null; prompt_hint: string; applicable_labels: RegionLabel[]; durability_years: number | null; maintenance: string };
export type Job = { id: string; type: string; status: "queued" | "running" | "done" | "failed"; error: string | null; result: Record<string, unknown> | null };
export type Assignment = { id?: string; region_id: string; material_id: string; color_hex: string | null };
export type Design = { id: string; project_id: string; name: string; is_active: boolean; assignments: Assignment[]; created_at: string; updated_at: string };
