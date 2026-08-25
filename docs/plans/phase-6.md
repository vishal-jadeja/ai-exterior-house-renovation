# Phase 6 — Report generation (1.5h)

## Goal
A downloadable PDF the homeowner can hand to a contractor.

## Scope (spec 5.8)
- Jinja2 HTML template → WeasyPrint PDF (report job in worker).
- Contents: project summary, original vs redesigned images, region table with areas + method,
  selected materials, quantities with wastage, cost breakdown, assumptions, limitations, disclaimer.
- Stored in object storage; presigned download.

## Checklist
- [x] `POST /designs/{id}/report`, `GET /reports/{id}` (status + URL)
- [x] Template + job handler
- [x] Web download button with progress

## Acceptance criteria
- PDF opens and contains both images, materials, quantities, costs.

## Outcome notes
- Uses `reportlab` (not WeasyPrint as originally planned) — no system libs (pango/cairo) needed, smaller Docker image, same output quality for this tabular layout.
- Caught and fixed during manual verification: the base-14 PDF fonts have no glyph for ₹, and plain (non-Paragraph) table cells silently overlapped instead of wrapping — both fixed (ASCII “Rs.” prefix, all cost cells now Paragraphs).
