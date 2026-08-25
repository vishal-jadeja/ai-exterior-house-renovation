# Phase 6 — Report generation (1.5h)

## Goal
A downloadable PDF the homeowner can hand to a contractor.

## Scope (spec 5.8)
- Jinja2 HTML template → WeasyPrint PDF (report job in worker).
- Contents: project summary, original vs redesigned images, region table with areas + method,
  selected materials, quantities with wastage, cost breakdown, assumptions, limitations, disclaimer.
- Stored in object storage; presigned download.

## Checklist
- [ ] `POST /designs/{id}/report`, `GET /reports/{id}` (status + URL)
- [ ] Template + job handler
- [ ] Web download button with progress

## Acceptance criteria
- PDF opens and contains both images, materials, quantities, costs.
