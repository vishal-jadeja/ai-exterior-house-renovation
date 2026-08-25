"""Building-surface taxonomy (spec 5.2) and its mapping from ADE20K classes."""

from __future__ import annotations

LABELS = ("wall", "window", "door", "balcony", "railing", "pillar", "parapet", "gate", "roof_edge")

# ADE20K label name → our label. Anything else is background.
ADE_TO_LABEL: dict[str, str] = {
    "wall": "wall",
    "building": "wall",
    "house": "wall",
    "windowpane": "window",
    "window": "window",
    "door": "door",
    "screen door": "door",
    "double door": "door",
    "railing": "railing",
    "bannister": "railing",
    "fence": "gate",
    "column": "pillar",
    "pole": "pillar",
    "awning": "roof_edge",
    "canopy": "roof_edge",
}

# CMP Facade dataset label name → our label (primary model: SegFormer fine-tuned on CMP Facade).
CMP_TO_LABEL: dict[str, str] = {
    "facade": "wall",
    "facade_wall": "wall",
    "window": "window",
    "blind": "window",
    "door": "door",
    "shop": "door",
    "balcony": "balcony",
    "pillar": "pillar",
    "cornice": "parapet",
}

MODEL_LABEL_MAPS = {**ADE_TO_LABEL, **CMP_TO_LABEL}

# Labels that are openings/attachments *inside* walls and must be subtracted from wall area.
OPENING_LABELS = ("window", "door", "railing", "balcony", "gate")

# Display colours (hex) for the editor and report.
LABEL_COLORS = {
    "wall": "#f97316",
    "window": "#3b82f6",
    "door": "#a855f7",
    "balcony": "#14b8a6",
    "railing": "#22c55e",
    "pillar": "#eab308",
    "parapet": "#ec4899",
    "gate": "#6366f1",
    "roof_edge": "#64748b",
}

HUMAN = {
    "wall": "Wall",
    "window": "Window",
    "door": "Door",
    "balcony": "Balcony",
    "railing": "Railing",
    "pillar": "Pillar / column",
    "parapet": "Parapet",
    "gate": "Gate / fence",
    "roof_edge": "Roof edge",
}
