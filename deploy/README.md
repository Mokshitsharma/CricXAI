# Deploying CricXAI

## Local — full mock slice

```bash
python -m scripts.mock_data --num-matches 100 --seed 42
python -m scripts.build_features
python -m scripts.train
python -m uvicorn app.api.main:app --reload --port 8000
```

Or `make demo`. API docs at http://localhost:8000/docs, OpenAPI at
`/v1/openapi.json`.

## Local — containers

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Brings up `api` (8000), `web` (3000), `postgres` (5432), `redis` (6379).
The API mounts `../data` read-only for models + processed CSVs, so run the
three pipeline commands above first. Postgres/Redis are wired for Phase 3;
the API works without them.

## Cloud — Render

`deploy/render.yaml` is a blueprint: connect the repo in Render or run
`render blueprint launch`. It provisions the API (Docker), the web app,
managed Postgres, and Redis, and wires the env vars between them. A 1 GB
disk is mounted at `/data` for model artifacts until Phase 3 moves them to
object storage.

For Fly.io instead, add a `deploy/fly.toml` pointing at `deploy/Dockerfile`
and attach Fly Postgres + Upstash Redis.

## Environment

Copy `.env.example` → `.env`. The only vars the mock slice needs are
`CRICXAI_MODEL_DIR` and `CRICXAI_PROCESSED_DIR` (both default to `data/*`).

## Model artifacts in the image

The API image does **not** bundle models by default — mount them or pull
from object storage at boot (`CRICXAI_MODEL_DIR`). For a throwaway demo
image, uncomment the two `COPY data/...` lines in `deploy/Dockerfile`.

## CI

`.github/workflows/ci.yml`: ruff lint → generate a 60-match mock dataset →
build features → train → `pytest` (unit + leakage + model smoke + API
contract) → build the API Docker image. The `web` job is `continue-on-error`
until the frontend is fleshed out.

`.github/workflows/scrape.yml` is disabled until real series IDs exist.
