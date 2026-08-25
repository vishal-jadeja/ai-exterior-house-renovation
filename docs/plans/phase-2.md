# Phase 2 — Structure identification & review editor (3.5h)

## Goal
Turn the uploaded photo into a mapped representation of the facade the user can review and fix.

## Scope (spec 5.2)
- Segmentation job: SegFormer fine-tuned on the CMP Facade dataset (ADE20K model evaluated and rejected: it labels the whole facade as `building`) on CPU → class masks → taxonomy
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
- [x] `POST /projects/{id}/segment` enqueues job; `GET /jobs/{id}` status
- [x] `services/segmentation.py` + `services/region_mapper.py` (unit-tested on synthetic masks)
- [x] `providers/vision/gemini.py` + `NoopRefiner`
- [x] `GET|PUT /projects/{id}/regions`
- [x] Web region editor
- [x] Model weights cached in the `models` volume

## Acceptance criteria
- Sample house → walls, windows, railing/balcony, pillars detected and drawn over the photo.
- User edits persist and survive reload; segmentation can be re-run without losing user regions
  (user regions kept, model regions replaced).

## Outcome notes
- ADE20K SegFormer was tried first; on real facades 87% of pixels are `building` and windows never win, so it was replaced by `Xpitfire/segformer-finetuned-segments-cmp-facade` (window/door/balcony/pillar/cornice classes, ~0.5s/image CPU). Both label maps are supported by `taxonomy.MODEL_LABEL_MAPS`.
- Gemini refinement is implemented and feature-flagged (`GEMINI_API_KEY`); without a key the pipeline uses `NoopRefiner`.
