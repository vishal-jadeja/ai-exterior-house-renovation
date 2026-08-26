# Deployment

## Local — Docker Compose (the reviewer path)

```sh
make up        # = cp -n .env.example .env && docker compose -f infra/docker-compose.yml up --build -d
make logs
make down      # add `-v` to docker compose to drop volumes (DB, MinIO, model cache)
```

Services: `postgres` (5433 on the host), `minio` (9000 API / 9001 console), `api` (8000),
`worker`, `web` (3000). `api` runs `alembic upgrade head` and seeds the catalog on every start;
`worker` and `web` wait for `api` to be healthy. Model weights are cached in the `models`
volume (`HF_HOME=/models`); the first segmentation job downloads them (network required).

Running `docker compose` directly (not via `make`) requires `.env` to exist.

`NEXT_PUBLIC_API_URL` is baked into the web image at **build** time (`infra/Dockerfile.web`
`ARG`, set in `docker-compose.yml`), and `CORS_ORIGINS` on the API must list the web origin.

## Cloud (free tiers, no credit card)

This layout needs no payment method anywhere. The API+worker container carries **no local ML
model** (`infra/Dockerfile.free`, no torch/transformers): Gemini is the primary detector
(`DETECTION_PROVIDER=gemini`), and diffusion renders are HTTP calls (Cloudflare Workers AI / fal)
with the local compositor as the always-available floor. `render.yaml` is the ready blueprint.

| Piece | Target | Notes |
|---|---|---|
| Web | Vercel | `apps/web`, env `NEXT_PUBLIC_API_URL=https://<app>.onrender.com` (baked at build time). |
| API + worker | Render (Docker, free) | `render.yaml` → `infra/Dockerfile.free`; `infra/space-entrypoint.sh` runs `alembic upgrade head`, `python -m app.seed`, then the worker + uvicorn in one container on `$PORT`. Free service sleeps when idle (cold start on first hit). Hugging Face Space (Docker) works too. |
| Postgres | Supabase | `DATABASE_URL=postgresql+asyncpg://postgres:<pwd>@<host>:5432/postgres?ssl=require`. |
| Object storage | Supabase Storage (S3) | Create bucket `renovation` and S3 access keys (Storage → S3). `S3_ENDPOINT_URL=S3_PUBLIC_ENDPOINT_URL=https://<ref>.storage.supabase.co/storage/v1/s3`, `S3_REGION=<project region>` (e.g. `us-east-1` — Supabase validates it, so **not** `auto`). Add a bucket CORS rule allowing `GET` from the web origin — the region editor loads the photo into a canvas via the presigned URL. |
| Structure detection | Gemini | `DETECTION_PROVIDER=gemini` + `GEMINI_API_KEY` (Google AI Studio, free, no card). Detects the full facade; regions stay editable on the canvas. |

Production checklist (enforced by `APP_ENV=prod` at boot):
- `JWT_SECRET` random, ≥ 32 chars
- `COOKIE_SECURE=true`; set `COOKIE_DOMAIN` if web and API share a parent domain, otherwise
  the refresh cookie is `SameSite=None` and needs HTTPS on both ends
- `S3_ACCESS_KEY` / `S3_SECRET_KEY` not the MinIO defaults
- `CORS_ORIGINS` = the Vercel origin only (no localhost)
- OpenAPI docs are disabled in prod automatically

AI keys: `GEMINI_API_KEY` drives structure detection when `DETECTION_PROVIDER=gemini` (and refines
regions when the local SegFormer is used); `FAL_KEY` and/or `CF_ACCOUNT_ID` + `CF_API_TOKEN` add
diffusion renders. With the local SegFormer (`DETECTION_PROVIDER=segformer`) and the built-in
compositor the app runs end to end with no keys at all; the free cloud layout above instead relies
on `GEMINI_API_KEY` for detection, since it ships without the local model.

## CI

`.github/workflows/ci.yml`:
- **api** — ruff, ruff format, mypy, pytest (SQLite), then `alembic upgrade head` + double seed
  against a Postgres service
- **web** — eslint, tsc, `next build`
- **compose** — builds both images, starts postgres/minio/api, waits for the api healthcheck and
  asserts the catalog seeded. This is the only job that exercises the Dockerfiles and in-container
  path resolution.
