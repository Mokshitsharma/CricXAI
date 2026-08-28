# CricXAI — Implementation Plan

Status: Draft v1 · Last updated: 2026-08-28

Task-level plan, ordered, with the files each task touches and its done
criteria. Grouped into sprints (~1 week each, solo pace). Phase mapping in
[PHASES.md](PHASES.md).

Legend: ☐ todo · ◑ in progress · ☑ done (this session)

---

## Sprint 1 — Mock data & feature table  (Phase 1)

### T1.1 ☑ Mock squads + ODI simulator
- **Files:** `scripts/mock_data.py`, `app/utils/cricket_constants.py` (reuse).
- 10 teams (India, Australia, England, South Africa, New Zealand, Pakistan,
  Sri Lanka, Bangladesh, Afghanistan, West Indies), ~15-player probable-2027
  squads with `role`, `batting_hand`, `bowler_type`, `batting_skill`,
  `bowling_skill` (0–1, illustrative).
- Deterministic ball-by-ball simulator: phase-aware bowler selection,
  length/line sampling from bowler tendency + phase, dismissal probability
  from batsman vs bowler skill + length/line danger + pressure, outcome
  multinomial, dismissal-type conditioned on length/line, shot-type sample.
- **Output:** `data/processed/deliveries.csv` + `matches.csv`, schema
  identical to `nlp_parser.py`, plus `source="mock"`, `series_id="MOCK"`.
- **Done:** `py -3.13 -m scripts.mock_data --num-matches 100 --seed 42`
  writes both CSVs; row counts sane (~28–32k deliveries); every batsman has
  ≥ 5 dismissals across the set.

### T1.2 ☑ Feature build on mock data
- **Files:** `scripts/build_features.py` (no change expected; fix only if the
  mock exposes a bug).
- **Done:** `py -3.13 -m scripts.build_features` produces
  `data/processed/delivery_features.csv` with all DR-15 columns, no NaNs in
  numeric feature columns, historical columns non-trivial.

### T1.3 ☑ Mock-data tests
- **Files:** `tests/scripts/test_mock_data.py`.
- Determinism (same seed → identical DataFrame), schema match vs parser
  output columns, value ranges, wickets-per-innings distribution sane.

---

## Sprint 2 — Model training  (Phase 1)

### T2.1 ☑ Training pipeline
- **Files:** `scripts/train.py`, `app/ml/__init__.py`, `app/ml/features.py`
  (shared feature-column list + selector).
- M1 `dismissal_prob`: LightGBM binary + `CalibratedClassifierCV`;
  `GroupKFold(match_id)`; metrics Brier, log loss, ROC-AUC, PR-AUC,
  reliability bins.
- M2 `dismissal_type`: LightGBM multiclass on `is_wicket` rows,
  `dismissal_type_encoded` ≥ 0; macro-F1, confusion matrix.
- M3 `expected_runs`: LightGBM regressor on `total_runs`; MAE, RMSE.
- **Artifacts:** `data/models/<model_id>/<version>/{model.pkl, meta.json,
  eval.md, shap_background.parquet}`; `data/models/active.json` pointer.
- **Done:** `py -3.13 -m scripts.train` runs end to end on mock features;
  writes 3 model dirs + `active.json` + a combined `data/models/EVAL.md`;
  M1 grouped-CV Brier ≥ 10% better than base rate (mock sanity bar).

### T2.2 ☑ Model registry loader
- **Files:** `app/ml/registry.py`.
- `load_active_models()` reads `active.json` (or `CRICXAI_MODEL_DIR`),
  returns a struct with fitted models + versions + feature lists + SHAP
  backgrounds. Raises a typed `NoActiveModelError` cleanly.
- **Done:** unit test loads the mock-trained models.

### T2.3 ☑ Training smoke + eval-schema tests
- **Files:** `tests/models/test_train_smoke.py`.
- Train on a 3-match fixture; assert artifacts + `meta.json` keys + SHAP
  values produced.

---

## Sprint 3 — Recommendation engine  (Phase 1)

### T3.1 ☑ Candidate grid + scoring
- **Files:** `app/engine/__init__.py`, `app/engine/candidates.py`,
  `app/engine/objective.py`, `app/engine/recommend.py`.
- Build `BALL_LENGTHS × BALL_LINES` candidates for the fixed `bowler_type`;
  assemble each candidate's feature row from situation + batsman features +
  candidate encodings; score with M1 (P wicket) and M3 (E runs); rank by
  `objective(phase)` weights; return top-k.

### T3.2 ☑ Reason templates + SHAP
- **Files:** `app/engine/reasons.py`, `app/ml/explain.py`.
- SHAP TreeExplainer on M1 for the chosen candidate; map top contributing
  features to cricket-language sentences with dataset-average deltas;
  `confidence` from batsman sample size + probability margin.

### T3.3 ☑ Field placement heuristic
- **Files:** `app/engine/field.py`, `app/engine/field_presets.py`.
- Map `(phase, length, line)` + batsman scoring-zone tendency → a named
  preset + 9 positions. Pure lookup + small rules for v1.

### T3.4 ☑ Engine tests
- **Files:** `tests/engine/test_recommend.py`.
- Deterministic ranking given fixed models; top-k shape; reasons non-empty
  for a high-sample batsman; low-sample flips confidence.

---

## Sprint 4 — API  (Phase 1)

### T4.1 ☑ FastAPI app + schemas
- **Files:** `app/api/main.py`, `app/api/schemas.py`, `app/api/deps.py`,
  `app/api/routers/{recommendation,batsmen,matches,reference,health}.py`.
- Endpoints per TRD §5.2 (recommendation, predict/dismissal, batsmen,
  batsmen/{id}/profile, matches, matches/{id}/timeline, reference, healthz,
  readyz). Reads mock CSVs via a small data-access layer (`app/api/data.py`)
  until Phase 3 Postgres.
- Error envelope, `X-Request-Id`, OpenAPI at `/v1/openapi.json`.

### T4.2 ☑ Data access layer (CSV-backed)
- **Files:** `app/api/data.py`.
- Load `deliveries`, `matches`, `delivery_features` into memory (pandas) at
  boot; batsman list, profile aggregates, match timeline, per-batsman feature
  lookup. Swappable for a DB impl later (same interface).

### T4.3 ☑ API contract tests
- **Files:** `tests/api/test_contract.py`.
- TestClient: happy path recommendation; 422 unknown batsman; 400 bad over;
  reference enums; healthz/readyz.

### T4.4 ☐ Quota + API-key middleware (Phase 5 — stub now)
- `app/api/security.py` with a no-op principal in Phase 1, real in Phase 5.

---

## Sprint 5 — Web console  (Phase 1)

### T5.1 ☑ Design canvas
- Design-canvas artboards: Console (light/dark), Batsman profile, Match
  timeline, Account. Tokens per DESIGN.md §2. Sources in `web/design/`.

### T5.2 ◑ Next.js scaffold
- **Files:** `web/` — Next.js 14 App Router, TS strict, Tailwind + tokens,
  TanStack Query, generated `/v1` client.
- Routes: `/`, `/console`, `/batsmen`, `/batsmen/[id]`, `/matches`,
  `/matches/[id]`, `/account` (stub).

### T5.3 ◑ Console components
- `SituationBuilder`, `RecommendationCard`, `AlternativesList`,
  `LengthLineHeatmap` (SVG), `FieldDiagram` (SVG), `ConfidenceBadge`,
  state components (loading/empty/error/low-sample/no-model).

### T5.4 ☐ Profile + match browser pages
- SSR profile with `VulnerabilityPanel`; match list + timeline with
  "Analyse" handoff to `/console` via query string.

### T5.5 ☐ E2E
- **Files:** `web/e2e/console.spec.ts` (Playwright): builder → recommendation
  renders → reasons visible → pick alternative updates field.

---

## Sprint 6 — Deployment  (Phase 1)

### T6.1 ☑ Containerization
- **Files:** `deploy/Dockerfile` (API, multi-stage), `deploy/Dockerfile.web`,
  `deploy/docker-compose.yml` (api + web + postgres + redis),
  `.dockerignore`.

### T6.2 ☑ CI
- **Files:** `.github/workflows/ci.yml` — lint (ruff), `pytest tests/`,
  leakage + extraction-quality gates, build API image, `web` typecheck +
  build.

### T6.3 ☑ Deploy config
- **Files:** `deploy/render.yaml` (or `deploy/fly.toml`), `deploy/README.md`
  with the deploy runbook; `.env.example`.

### T6.4 ☑ Makefile / task runner
- **Files:** `Makefile` — `mock`, `features`, `train`, `demo`, `api`, `web`,
  `test`, `lint`, `docker-up`.

### T6.5 ☐ Scheduled scrape workflow (Phase 2)
- **Files:** `.github/workflows/scrape.yml` — daily, small batch, alert on
  failure. Left disabled until real series IDs exist.

---

## Sprint 7+ — Phase 2/3 (summary, planned)

- Fill `TOURNAMENTS` series IDs; enable scrape workflow; golden fixtures;
  name-resolution table; retrain on real data; wire low-sample everywhere.
- Alembic migrations for BACKEND_SCHEMA.md; `scripts/load_db.py`; swap
  `app/api/data.py` CSV impl for a Postgres impl behind the same interface;
  Redis cache + `models` table registry; object storage for artifacts.
- Sentry, OpenTelemetry, dashboards, alerts.

---

## Dependency graph (Phase 1)

```
T1.1 ─► T1.2 ─► T2.1 ─► T2.2 ─► T3.1 ─► T3.2 ─► T4.1 ─► T4.3
                       └► T2.3        T3.3 ─┘     T4.2 ─┘
T5.1 ─► T5.2 ─► T5.3 ─► T5.4 ─► T5.5     (T5.3 needs T4.1 running)
T6.1..T6.4 parallel; T6.2 needs T1.3/T2.3/T4.3
```

## This session's scope

T1.1–T1.3, T2.1–T2.3, T3.1–T3.4, T4.1–T4.3, T5.1, T6.1–T6.4, plus a
`web/` scaffold (T5.2/T5.3 partial). Remaining items are marked ☐/◑.
