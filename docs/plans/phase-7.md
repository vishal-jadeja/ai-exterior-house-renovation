# Phase 7 — Docs, deployment & polish (2.5h)

## Goal
Reviewer-ready: one-command local run, live demo URL, and the documentation deliverables.

## Scope (spec 9)
- `README.md`: what it is, quick start (compose), env keys, demo script, screenshots.
- `docs/architecture.md` (Mermaid), `docs/user-workflow.md`, `docs/estimation.md` (how numbers are
  derived, formulas, assumptions), `docs/limitations.md`, `docs/deployment.md`.
- Deploy: web → Vercel; api + worker → Hugging Face Space (Docker, one container, supervisord);
  Postgres → Neon; storage → Cloudflare R2.
- Demo assets: `samples/` facade photos, seed textures.
- Polish: loading states, error toasts, empty states.

## Checklist
- [x] Docs written (README.md, docs/architecture.md, user-workflow.md, estimation.md, limitations.md, deployment.md)
- [ ] Cloud deployment live and smoke-tested
- [ ] Clean-clone `docker compose up` verified

## Acceptance criteria
- A reviewer can run the app locally in <5 min and open the live URL.
