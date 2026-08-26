# How the estimation works

All estimation code is pure and lives in `apps/api/app/services/`:
`scale_estimator.py` → `area_estimator.py` → `quantity_engine.py` → `cost_engine.py`, orchestrated
by `estimation.py`. Every number in the UI and PDF comes with the assumption that produced it.

## 1. Pixel → feet scale (`scale_estimator.py`)

The photo has no absolute scale, so one is inferred. Sources are tried in order of reliability
and the first that applies wins; the chosen method and its confidence are stored on the project
and printed in the report.

| Priority | Reference | Formula | Confidence |
|---|---|---|---|
| 1 | User-entered facade width and/or height | `ft_per_px = W_ft / silhouette_w_px` (and/or height); with both, the **geometric mean** of the two factors so the user's `W × H` product is preserved exactly | high |
| 2 | Detected main door (aspect 1.3–4.5) | `ft_per_px = 7 ft / door_h_px` | medium |
| 3 | ≥ 2 detected windows | `ft_per_px = 4 ft / median(window_h_px)` | medium |
| 4 | Floor count entered by user | `ft_per_px = floors × 10 ft / silhouette_h_px` | low |
| 5 | Nothing else | `ft_per_px = 30 ft / silhouette_w_px` | low |

*Silhouette* is the bounding box of all wall + parapet regions. Standard sizes (door 7 ft,
window 4 ft, storey 10 ft, facade 30 ft) are typical for Indian low-rise residential buildings.

## 2. Surface area per region (`area_estimator.py`)

Each region polygon is rasterised at the photo's resolution.

- **Openings**: pixels of windows, doors, railings, balconies and gates form an *openings* mask that
  is subtracted from walls, parapets and pillars (`net_px = region_px − openings_px`). The report
  notes the percentage removed.
- **Foreshortening**: a surface photographed at an angle appears smaller than it is. For
  quadrilateral-ish regions the ratio of opposite edge lengths gives a correction factor `fs`
  (1.0 for an axis-aligned rectangle, capped at 1.4). It is applied only where noted below.

| Label | Area formula | Running length |
|---|---|---|
| wall, parapet | `net_px × ft_per_px² × fs` | parapet: `bbox_w × ft_per_px` (for coping) |
| pillar | `h_ft × (w_ft + 2 × 1 ft)` — front face plus two visible sides, assumed 1 ft deep (3 of 4 faces) | — |
| railing, roof_edge | face area `px × ft_per_px² × fs` | `polyline_length × ft_per_px` (follows slope; at least bbox width) |
| balcony | face area with any railing region drawn on it excluded (priced separately) | same as railing |
| gate | `bbox_w × bbox_h × ft_per_px²` | `bbox_w × ft_per_px` |
| window, door | informational only — never priced | — |

Materials priced per **sqft** use the area; materials priced per **rft** (railings, coping) use
the running length.

## 3. Quantities (`quantity_engine.py`)

```
base          = area_sqft  (or length_ft for rft materials)
with_wastage  = base × (1 + wastage_pct / 100)         # per material, e.g. 5 % paint, 10 % tiles
```

Then by the material's purchase unit:

| Purchase unit | Quantity | Packs |
|---|---|---|
| litre (paint) | `with_wastage × coats / coverage_sqft_per_L` | 10 L cans, rounded up |
| kg (texture) | `with_wastage × coats / coverage_sqft_per_kg` | 25 kg bags |
| piece (tiles, stone, brick slips) | `ceil(with_wastage / piece_area)` pieces, then **rounded up to whole boxes** (`pieces_per_box`) — you buy boxes, not loose tiles | boxes |
| sheet (HPL, ACP, louvers) | `ceil(with_wastage / sheet_area)` | sheets |
| rft (railings, coping) | `with_wastage` | posts at 5 ft spacing + 1 |
| sqft (fabricated gate) | `with_wastage` | — |

Coverage, coats, piece size, box size and wastage come from `seed/materials.json` and are shown
next to each line.

## 4. Costs (`cost_engine.py`)

```
material_cost = quantity_purchased × material_rate      # rate per purchase unit (₹/L, ₹/piece, ₹/rft…)
labor_cost    = base_surface      × labor_rate          # rate per sqft or rft of surface
line_total    = material_cost + labor_cost
category subtotal = Σ lines in category;  grand_total = Σ material + Σ labour
```

Rates default from the catalog; a project-level **rate card** overrides any material's rates
without touching other projects. Currency is a label on the project (default INR) — rates are not
converted.

## 5. Staleness

Each stored estimate records a SHA-256 fingerprint of: user measurements, currency, source image
(id + dimensions), active region polygons and labels, region→material assignments, the rates in
effect, and the catalog properties (coverage, coats, wastage, box size) of the materials used.
If any of these differ now, the estimate is flagged `stale`, the UI shows a banner, and report
generation is refused until it is recalculated. Estimates are versioned per design, never
overwritten.

## Worked example

Wall region: 412 000 net px after subtracting three windows; photo scale from a detected door of
310 px → `ft_per_px = 7/310 = 0.02258`; `fs = 1.06` (slight angle).

```
area          = 412000 × 0.02258² × 1.06  ≈ 222.7 sqft
Premium emulsion: wastage 5 %, 2 coats, coverage 120 sqft/L
with_wastage  = 233.8 sqft
litres        = 233.8 × 2 / 120 = 3.9 L  → 1 can of 10 L
material_cost = 3.9 × ₹540/L   = ₹2 106
labor_cost    = 222.7 × ₹16/sqft = ₹3 563
line_total    ≈ ₹5 669
```

The report prints exactly these intermediate values per line.
