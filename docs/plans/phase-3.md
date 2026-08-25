# Phase 3 — Material catalog & designs (2h)

## Goal
Let the user pick materials per region and keep several design variants side by side.

## Scope (spec 5.3)
- Seeded catalog (`seed/materials.json`, ~16 items): exterior paint, texture finish, stone cladding,
  brick cladding, vitrified/porcelain tiles, glass railing, SS railing, MS railing, WPC/ACP panels.
  Each: unit, coverage/piece size, wastage %, material + labor rate, currency, texture asset,
  prompt hint, applicable labels, durability, maintenance.
- Design CRUD per project; exactly one active design; clone design.
- Assignment: region → material (+ optional color for paint).
- Web: material picker filtered by region label, design tabs, "duplicate design".

## Checklist
- [ ] `GET /materials`
- [ ] `GET|POST /projects/{id}/designs`, `PATCH|DELETE /designs/{id}`, `POST /designs/{id}/clone`
- [ ] `PUT /designs/{id}/assignments` (bulk)
- [ ] Seed textures (CC0) in `seed/textures`, uploaded to storage on seed
- [ ] Web design panel

## Acceptance criteria
- Two designs with different assignments saved; switching tabs swaps assignments instantly.
