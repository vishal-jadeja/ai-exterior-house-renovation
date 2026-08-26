# Limitations

This is a 24-hour prototype. Costs it produces are **advisory planning figures**, not quotations.

## Measurement accuracy
- **Single photo, no depth.** All areas are projected face areas scaled by one inferred
  pixel-to-feet factor. Expect ±15–25 % on well-shot frontal photos with a known facade width,
  and considerably worse when the scale falls back to a default assumption. The report always
  states which reference was used and its confidence.
- **Perspective correction is approximate.** Foreshortening is estimated from region edge ratios,
  capped at ×1.4, and applied to walls, parapets, railings and balconies only; pillars and gates
  use bounding-box formulas.
- **Return faces are guessed.** Pillars are assumed 1 ft deep with three visible faces; side walls
  not in the photo are not counted. Photograph each elevation as a separate project if needed.
- **Only what the camera sees.** Surfaces hidden behind trees, vehicles or the compound wall are
  not measured.

## Structure identification
- The default segmentation model (SegFormer fine-tuned on CMP Facade) detects walls, windows,
  doors, balconies, pillars and cornices. **Railings and gates are not among its classes**; they
  appear only when a Gemini key is configured (which adds/relabels regions from the photo) or when
  drawn by hand in the editor. Parapet and roof-edge regions are derived geometrically from the
  wall silhouette and carry low confidence.
- Detection is tuned for low-rise residential facades photographed roughly frontally. Strongly
  angled shots, night photos, heavily occluded facades and glass-curtain buildings degrade sharply.
- One photo per project. Replacing the photo deactivates its regions (material choices are kept
  where a region still exists, and everything downstream is marked stale).

## Visualization
- Without hosted providers, the **local compositor** maps a texture swatch / colour onto each
  region with the original shading. It is convincing for paint and flat cladding, less so for
  railings, three-dimensional stone or changed geometry. It never alters openings or structure.
- Diffusion-based renderers (fal.ai, Cloudflare Workers AI) give more realistic results but may
  hallucinate details; the provider used is recorded on every render.
- Lighting, shadows and reflections are not physically simulated.

## Catalog and costs
- The catalog is a curated **17-material sample** with typical Indian rates (INR). Rates vary by
  city and season; edit them in the rate card. Currency is a label — no conversion is performed.
- Doors and windows are measured for scale and opening subtraction but are **not priced**; the
  catalog has no door/window materials.
- Labour is priced per unit of surface only; scaffolding, transport, surface preparation, primer,
  demolition, taxes and contractor margin are not modelled. Wastage percentages are fixed per
  material, not per site.
- No structural, waterproofing or regulatory checks are implied.

## Platform
- Rate limiting is in-process (per API replica) and the segmentation model is serialised per
  worker process; scale by adding worker replicas.
- Presigned image links expire after 15 minutes; a page left open longer needs a reload.
- The region editor is mouse/touch only; keyboard editing of polygons is not implemented.
- Text and units are English/feet only.
