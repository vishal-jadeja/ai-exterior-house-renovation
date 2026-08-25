.PHONY: up down logs api web worker test lint seed migrate fmt

up:            ## Start full stack (postgres, minio, api, worker, web)
	docker compose -f infra/docker-compose.yml up --build -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f api worker web

infra:         ## Only databases for local dev
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
	cd apps/api && ruff check . && cd ../web && pnpm lint

fmt:
	cd apps/api && ruff format . && ruff check --fix .
