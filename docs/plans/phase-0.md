# Phase 0 — Scaffold & infrastructure (1h)

## Goal
A running monorepo skeleton: web + api + worker + postgres + minio via Docker Compose, with the
full data model, settings, security middleware, job queue, and CI in place so every later phase
only adds features.

## Scope
- Monorepo layout: `apps/web` (Next.js 15/TS), `apps/api` (FastAPI), `infra/`, `docs/`, `seed/`, `samples/`
- `pydantic-settings` config; `.env.example`; secrets never in code
- SQLAlchemy 2 async models for the whole domain (users, projects, images, regions, materials,
  rate_cards, designs, design_assignments, renders, estimates, reports, jobs)
- Alembic with initial migration
- Postgres-backed job queue + worker loop (`FOR UPDATE SKIP LOCKED`, retries, stale-lock reclaim)
- Security middleware: CORS allowlist, rate limiting, request-id logging, security headers
- Docker Compose (postgres, minio, api, worker, web), multi-stage Dockerfiles, non-root users
- GitHub Actions CI (ruff + pytest, eslint + tsc)

## Checklist
- [x] Next.js app created (App Router, TS, Tailwind)
- [x] FastAPI app with settings, logging, DB session, security helpers, deps
- [x] All domain models defined
- [x] Worker + job registry + seed script
- [x] Dockerfiles + compose + Makefile + CI
- [x] Alembic initial migration generated and applied
- [x] `/health` returns ok against compose Postgres
- [x] Web renders a landing page and reads `NEXT_PUBLIC_API_URL`

## Acceptance criteria
- `make up` → `http://localhost:3000` loads and `http://localhost:8000/health` returns `{"status":"ok"}`
- `make test` passes (smoke test)
