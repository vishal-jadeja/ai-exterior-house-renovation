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

## Cloud (planned layout, free tiers)

| Piece | Target | Notes |
|---|---|---|
| Web | Vercel | `apps/web`, env `NEXT_PUBLIC_API_URL=https://<space>.hf.space` |
| API + worker | Hugging Face Space (Docker) | One container from `infra/Dockerfile.api` running `alembic upgrade head && python -m app.seed`, then uvicorn and `python -m app.worker` under a small supervisor (or `sh -c "python -m app.worker & uvicorn …"`). Persistent `/models` needs a paid persistent-storage Space or accept re-download on restart. |
| Postgres | Neon | `DATABASE_URL=postgresql+asyncpg://…?ssl=require` |
| Object storage | Cloudflare R2 | `S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`, `S3_PUBLIC_ENDPOINT_URL` the same (or a custom domain), `S3_REGION=auto`. Add a CORS rule on the bucket allowing `GET` from the web origin — the region editor loads the photo into a canvas. |

Production checklist (enforced by `APP_ENV=prod` at boot):
- `JWT_SECRET` random, ≥ 32 chars
- `COOKIE_SECURE=true`; set `COOKIE_DOMAIN` if web and API share a parent domain, otherwise
  the refresh cookie is `SameSite=None` and needs HTTPS on both ends
- `S3_ACCESS_KEY` / `S3_SECRET_KEY` not the MinIO defaults
- `CORS_ORIGINS` = the Vercel origin only (no localhost)
- OpenAPI docs are disabled in prod automatically

Optional AI keys: `GEMINI_API_KEY` (region refinement), `FAL_KEY` and/or
`CF_ACCOUNT_ID` + `CF_API_TOKEN` (diffusion renders). Without them the app still works end to end
using the local model and compositor.

## CI

`.github/workflows/ci.yml`:
- **api** — ruff, ruff format, mypy, pytest (SQLite), then `alembic upgrade head` + double seed
  against a Postgres service
- **web** — eslint, tsc, `next build`
- **compose** — builds both images, starts postgres/minio/api, waits for the api healthcheck and
  asserts the catalog seeded. This is the only job that exercises the Dockerfiles and in-container
  path resolution.
