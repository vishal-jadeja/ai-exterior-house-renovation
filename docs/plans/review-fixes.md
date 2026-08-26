# Review fixes — remaining work

> **Status (2026-08-26): everything below is done** and committed in `d5ad9e7` + `b53949d`.
> A second senior review the same day found further demo-blocking issues (compose stack could not
> start, stale `app/models/` package shadowing `models.py`, orphaned design assignments producing
> ₹0 estimates) — fixed in the commits that follow `b53949d`; see `git log` and
> [phase-7.md](phase-7.md) for what remains (docs + deployment). The section headings below are
> kept as the original checklist.

Senior review of phases 0–6 (2026-08-25) found 3 demo-breaking bugs, several silent
data-loss / wrong-money bugs and a set of UX/hygiene gaps. Full findings: the review plan in
`~/.claude/plans/as-a-senior-engineer-parsed-bachman.md`. This file tracks what is **already
applied in the working tree (uncommitted)** and what is **still to do**, so work can resume
from here.

Conventions for this work: no browser/extension verification needed; run the checks below,
then **commit (plain message, no trailers) and push** when everything passes.

---

## A. Already applied (uncommitted, tests green at last run except one now-fixed case)

Backend / infra:
- `.github/workflows/ci.yml` — installs `.[dev,report]`, runs `ruff format --check`, `mypy app`,
  Postgres service + `alembic upgrade head` + double seed, web `pnpm build`.
- `infra/docker-compose.yml` — api healthcheck, worker/web wait on `service_healthy`,
  `restart: unless-stopped`, MinIO curl probe.
- `Makefile` — `env` target (`cp -n .env.example .env`), `infra` in `.PHONY`, `typecheck`, format check.
- `alembic/versions/…material_quantity_unit.py` — `server_default="sqft"`.
- `app/routers/renders.py` — ownership query joins `Design.project_id` (fixes 500 with ≥2 designs);
  `job_id` always populated (resume polling after reload).
- `app/routers/reports.py` — same `job_id` change; `POST /report` 409s when estimate is stale.
- `app/worker.py` — loop wrapped in try/except, rollback before bookkeeping commit, exponential
  backoff via `created_at` push-forward, claim query honours `created_at <= now()`.
- `app/services/jobs.py` — `IntegrityError` on idempotency key → return winner.
- `app/routers/regions.py` — status set before enqueue commit; status never regresses;
  degenerate polygon → 422 (`MIN_REGION_PX`).
- `app/routers/images.py` — old photo `kind="superseded"` (no cascade delete), its regions
  soft-deactivated, `replaced_regions` in response, unique storage key per upload,
  Content-Length + chunked read cap, sanitize/assess via `asyncio.to_thread`.
- `app/schemas/project.py` — `UploadOut.replaced_regions`.
- `app/jobs.py` — re-segment soft-deactivates model regions (assignments survive); report uses
  active regions only; `build_report` via `to_thread`.
- `app/services/area_estimator.py` — real edge-ratio foreshortening, `_polyline_length` for
  railing/roof_edge/**balcony** (balcony now gets a length → non-zero rft cost), pillar
  `h×(w+2d)`, cv2 import dropped.
- `app/services/quantity_engine.py` — piece quantity = whole boxes purchased; notes use
  defaulted coverage/piece (no `None:g` crash).
- `app/services/scale_estimator.py` — geometric mean of width/height factors; zero-extent guard.
- `app/schemas/region.py` — finiteness check; `get_args(Label)`.
- `app/routers/estimates.py` — rewritten: `_fingerprint` of inputs stored in payload,
  `EstimateOut.stale`, `PATCH /measurements` uses `exclude_unset`, estimate via `to_thread`,
  `current_fingerprint`/`latest_estimate_row` helpers (used by reports).
- `app/schemas/estimate.py` — `stale: bool = False`.
- `app/routers/designs.py` — validate all assignments before deleting existing ones.
- `app/providers/render/diffusion.py` — per-region hole cutting.
- `app/core/ratelimit.py` — `X-Forwarded-For` aware key.
- `app/routers/auth.py` — argon2 via `to_thread`, precomputed `_DUMMY_HASH`.
- `app/core/config.py` — `_prod_guard` model validator (JWT secret, cookie_secure, S3 key).
- `app/main.py` — `openapi_url` hidden in prod; handler type-ignore.
- `pyproject.toml` — `[tool.mypy]` (`ignore_missing_imports`, `check_untyped_defs`).
- `app/services/segmentation.py` — upsample argmax/conf maps, not logits (OOM fix); `Resampling`.
- mypy nits in `services/images.py`, `report_builder.py`, `render/local.py`, `vision/gemini.py`.
- `tests/conftest.py` — `PRAGMA foreign_keys=ON`.

## B. Remaining — backend tests (must update/add before committing)

1. `tests/test_estimation_engines.py`
   - `test_quantities`: TILE now `quantity == 56` (7 boxes × 8), `packs == 7`.
   - Add: trapezoid wall → `foreshortening > 1.0`; axis-aligned rect → `== 1.0`.
   - Add: balcony region with `railing-glass`-style rft material → `length_ft > 0`, cost > 0.
   - Add: pillar area `== h_ft * (w_ft + 2)`; sloped railing polyline length > bbox width.
   - Add: `cost_engine.price` categories sum == grand_total; user width+height → geometric mean.
2. `tests/test_estimates_api.py`
   - After `PUT /rate-card`, `GET /designs/{id}/estimate` → `stale: true`; after `POST` → `false`.
   - `PATCH /measurements` with `{floors: 2}` only must keep an earlier `facade_width_ft`.
   - `POST /designs/{id}/report` → 409 when stale.
3. `tests/test_render.py::test_render_route_and_job` — create a second design (clone) before the
   `GET /renders/{id}` ownership assertions (regression for the `MultipleResultsFound` 500).
4. `tests/test_images.py` — re-upload keeps regions rows (inactive) and design assignments;
   response `replaced_regions == n`; oversize body → 413.
5. `tests/test_regions_api.py` — NaN polygon → 422; 3 collinear points → 422; `PUT /regions` on
   an `estimated` project leaves status unchanged.
6. New `tests/test_worker.py` — `_backoff_seconds`, and `_run_job` with a handler that raises
   after a failed flush leaves the job `queued`/`failed` and the worker alive (use SQLite
   session; skip `_claim_job` — Postgres-only SQL).
7. Run: `cd apps/api && ruff check . && ruff format --check . && mypy app && pytest -q`.

## C. Remaining — frontend (`apps/web/src`)

1. `lib/api.ts`
   - Format pydantic 422 lists: `detail.map(d => \`${d.loc.slice(1).join('.')}: ${d.msg}\`).join('; ')`.
   - `AbortSignal.timeout(30_000)` merged with caller signal; drop unused `raw` option.
   - Single in-flight `refreshAccessToken()` promise shared by concurrent 401s.
2. `lib/jobs.ts` — deadline param (default 10 min) → throw `"timed out"`; keep `signal` support.
3. `lib/types.ts` — `Estimate.stale: boolean`; `UploadOut.replaced_regions`.
4. `components/StructureStep.tsx`
   - Pass an `AbortController` signal to `waitForJob`, abort in `useEffect` cleanup.
   - "Re-detect" → `window.confirm` when regions exist (assignments on model regions will be reset).
   - `beforeunload` guard while `dirty`.
5. `components/UploadPanel.tsx` — client-side size check (10 MB) before POST; if the project
   already has regions, `confirm("Replacing the photo resets detected regions…")`; show
   `replaced_regions` in the success message.
6. `components/DesignStep.tsx` — wrap `createDesign/clone/activate/rename/remove` in one
   `guard(fn)` helper that sets `msg` on `ApiError`; `confirm` before delete.
7. `components/EstimateStep.tsx`
   - Rate inputs as strings (`edits: Record<string,{material_rate:string;labor_rate:string}>`),
     parse on apply; validate width/height ≥ 6 before PATCH with a friendly message.
   - Show a "Rates/regions changed — recalculate" banner when `est.stale`.
   - `CONF[...] ?? "bg-zinc-100"`.
8. `components/RenderStep.tsx` / `ReportStep.tsx` — on load, if latest record is
   `queued|running` with `job_id`, resume `waitForJob` (with abort on unmount) and show progress;
   selector gate `doneRenders.length > 1`.
9. `components/RegionEditor.tsx` — `onerror` → show "Could not load photo" message; reset `img`
   on `url` change and clear handlers on cleanup; wrap export with
   `next/dynamic(() => import(...), { ssr: false })` from `StructureStep`; `wrapW` initial
   from `wrapRef.current?.clientWidth`.
10. `app/projects/page.tsx` — surface load/create errors in an inline message.
11. Run: `cd apps/web && pnpm lint && pnpm exec tsc --noEmit && pnpm build`.

## D. Remaining — catalog / spec gaps

1. `seed/materials.json` — add `"roof_edge"` to a fascia paint/board entry and `"parapet"` to
   a coping/rft material; confirm railings list `"balcony"`.
2. `app/services/region_mapper.py` + `taxonomy.py` — emit `balcony` from CMP `balcony` class
   (map to `balcony`, not `railing`); remove the `continue` skip; add a `MIN_AREA_FRAC["balcony"]`.
   Update `tests/test_region_mapper.py` expectations and `docs/plans/phase-2.md` acceptance text.
3. `DesignStep.tsx` surfaces filter — stop hiding `roof_edge` once a material applies to it.

## E. Remaining — hygiene

1. Add `/.dockerignore` (`.git`, `**/.venv`, `**/node_modules`, `**/.next`, `**/.hf_cache`,
   `**/*.egg-info`, `*.pdf`, `scratch`).
2. `infra/Dockerfile.api` — `--index-url https://download.pytorch.org/whl/cpu` for torch;
   install `.[ml,report]` (no `dev`); copy `app/` before `pip install` instead of the stub package.
3. `infra/Dockerfile.web` — copy `pnpm-workspace.yaml` into the deps stage.
4. `git rm` `apps/api/renovation_api.egg-info/*`, `apps/web/public/{file,globe,next,vercel,window}.svg`,
   `apps/web/README.md`; add `*.egg-info/` to `.gitignore`.
5. `config.py` — wire `min_image_dimension` into `quality_gate.MIN_SIDE` and `segmentation_enabled`
   into `segment_job` (skip model, return empty candidates + guidance), or delete both.
6. `.env.example` — add the ~11 missing settings with defaults and comments.
7. `docs/plans/README.md` — add a row for this review-fix pass; tick phase-2 wording.

## F. Finish

1. `make lint typecheck test` (API + web) all green; `pnpm build` succeeds.
2. `git add -A && git commit -m "fix: address senior review findings (CI, worker, data loss, estimation math, UX)"`
   — plain message, no Co-Authored-By.
3. `git push origin main`.
