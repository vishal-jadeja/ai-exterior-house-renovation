# Phase 5 — Area, quantity & cost estimation (3h)

## Goal
Deterministic, explainable numbers: surface areas → material quantities → itemised costs, with
editable rates and instant recalculation.

## Scope (spec 5.5, 5.6, 5.7)
- Scale estimator (priority + confidence): user facade width/height → door height 7 ft → window
  height 4 ft → floors × 10 ft → default facade width 30 ft.
- Area estimator: `area_ft2 = px_area × scale² × foreshortening`; openings subtracted from walls;
  railing/parapet length; pillar surface = height × perimeter.
- Quantity engine: wastage, paint litres/buckets, tile pieces/boxes, cladding boxes, railing rft +
  posts, panels sheets.
- Cost engine: material cost, labor cost, category subtotals, grand total, currency.
- Rate cards: per-project override of catalog defaults; `PUT` → recalculated estimate (versioned).
- Web: measurements panel (optional inputs), estimate table with assumptions & confidence, inline
  rate editing.

## Checklist
- [ ] `services/scale_estimator.py`, `area_estimator.py`, `quantity_engine.py`, `cost_engine.py`
      (pure; golden-case tests)
- [ ] `PATCH /projects/{id}/measurements`, `GET|PUT /projects/{id}/rate-card`
- [ ] `POST /designs/{id}/estimate`, `GET /designs/{id}/estimate`
- [ ] Web estimate view

## Acceptance criteria
- Editing paint rate changes the total immediately; assumptions and confidence are visible.
