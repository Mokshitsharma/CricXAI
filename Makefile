# CricXAI task runner.
# Local dev on Windows without `make`: run the commands under each target
# directly, swapping `python` for `py -3.13` if that is your interpreter.

PYTHON ?= python
MATCHES ?= 100
SEED ?= 42

.PHONY: help mock features train models demo api web test lint fmt docker-up docker-down clean

help:
	@echo "mock      - generate mock ODI data ($(MATCHES) matches, seed $(SEED))"
	@echo "features  - build the leakage-free feature table"
	@echo "train     - train M1/M2/M3 and write data/models/"
	@echo "models    - mock + features + train"
	@echo "demo      - models, then run the API"
	@echo "api       - run the FastAPI dev server"
	@echo "web       - run the Next.js dev server (web/)"
	@echo "test      - pytest"
	@echo "lint      - ruff check"
	@echo "docker-up - docker compose up (api + web + postgres + redis)"

mock:
	$(PYTHON) -m scripts.mock_data --num-matches $(MATCHES) --seed $(SEED)

features:
	$(PYTHON) -m scripts.build_features

train:
	$(PYTHON) -m scripts.train

models: mock features train

demo: models api

api:
	$(PYTHON) -m uvicorn app.api.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check app scripts tests

fmt:
	$(PYTHON) -m ruff format app scripts tests

docker-up:
	docker compose -f deploy/docker-compose.yml up --build

docker-down:
	docker compose -f deploy/docker-compose.yml down -v

clean:
	rm -f data/processed/*.csv
	rm -rf data/models/*
