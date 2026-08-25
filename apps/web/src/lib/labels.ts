import type { RegionLabel } from "@/lib/types";

export const LABELS: RegionLabel[] = ["wall", "window", "door", "balcony", "railing", "pillar", "parapet", "gate", "roof_edge"];

export const LABEL_COLORS: Record<RegionLabel, string> = {
  wall: "#f97316",
  window: "#3b82f6",
  door: "#a855f7",
  balcony: "#14b8a6",
  railing: "#22c55e",
  pillar: "#eab308",
  parapet: "#ec4899",
  gate: "#6366f1",
  roof_edge: "#64748b",
};

export const LABEL_NAMES: Record<RegionLabel, string> = {
  wall: "Wall",
  window: "Window",
  door: "Door",
  balcony: "Balcony",
  railing: "Railing",
  pillar: "Pillar / column",
  parapet: "Parapet",
  gate: "Gate / fence",
  roof_edge: "Roof edge",
};
