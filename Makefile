.PHONY: up down logs infra api web worker test lint typecheck seed migrate fmt env

env:           ## Create .env from the example if missing
	@test -f .env || cp .env.example .env

up: env        ## Start full stack (postgres, minio, api, worker, web)
	docker compose -f infra/docker-compose.yml up --build -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f api worker web

infra: env     ## Only databases for local dev
	docker compose -f infra/docker-compose.yml up -d postgres minio

api:           ## Run API locally (needs .venv)
	cd apps/api && uvicorn app.main:app --reload --port 8000

worker:
	cd apps/api && python -m app.worker

web:
	cd apps/web && pnpm dev

migrate:
	cd apps/api && alembic upgrade head

seed:
	cd apps/api && python -m app.seed

test:
	cd apps/api && pytest -q

lint:
	cd apps/api && ruff check . && ruff format --check . && cd ../web && pnpm lint

typecheck:
	cd apps/api && mypy app && cd ../web && pnpm exec tsc --noEmit

fmt:
	cd apps/api && ruff format . && ruff check --fix .
