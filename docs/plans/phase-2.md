# Phase 2 — Structure identification & review editor (3.5h)

## Goal
Turn the uploaded photo into a mapped representation of the facade the user can review and fix.

## Scope (spec 5.2)
- Segmentation job: SegFormer (ADE20K) on CPU → class masks → taxonomy
  (wall, window, door, balcony, railing, pillar, parapet, gate, roof_edge) → polygons with
  pixel area, bbox, confidence.
- Heuristics: parapet = wall band above topmost opening; roof_edge = top boundary of building mask;
  building class falls back to wall.
- Gemini 2.5 Flash refinement (optional, `GEMINI_API_KEY`): relabel/add regions, estimate floors and
  a reference dimension. Strict JSON schema; any failure → keep model result.
- Regions API: list, bulk replace (user edits create `source=user`, bump version), relabel, delete.
- Web: canvas overlay (react-konva) with per-label colors, vertex drag, relabel, delete, add box,
  job progress polling.

## Checklist
- [ ] `POST /projects/{id}/segment` enqueues job; `GET /jobs/{id}` status
- [ ] `services/segmentation.py` + `services/region_mapper.py` (unit-tested on synthetic masks)
- [ ] `providers/vision/gemini.py` + `NoopRefiner`
- [ ] `GET|PUT /projects/{id}/regions`
- [ ] Web region editor
- [ ] Model weights cached in the `models` volume

## Acceptance criteria
- Sample house → walls, windows, railing/balcony, pillars detected and drawn over the photo.
- User edits persist and survive reload; segmentation can be re-run without losing user regions
  (user regions kept, model regions replaced).
