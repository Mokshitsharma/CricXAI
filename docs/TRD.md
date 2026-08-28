# CricXAI — Technical Requirements Document (TRD)

Status: Draft v1 · Owner: Engineering · Last updated: 2026-08-28

Companion to [PRD.md](PRD.md). This document turns product requirements into
technical requirements: what each subsystem must do, its interfaces,
constraints, and acceptance criteria.

---

## 1. System overview

```
ESPNcricinfo (unofficial APIs)
        │  scrape (idempotent, polite)
        ▼
   data/raw/{match_id}.json         ── object storage (prod)
        │  nlp_parser (phrase dictionaries, defensive field access)
        ▼
   deliveries + matches (CSV → Postgres)
        │  build_features (leakage-free)
        ▼
   delivery_features (CSV/parquet → Postgres / feature table)
        │  train (GBDT + calibration)
        ▼
   model registry  ──►  FastAPI service  ──►  Web console + REST API
        │                     │
        └── SHAP explainer ───┘
```

## 2. Technology stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| Language (backend/ML) | Python 3.11+ | Existing code; ML ecosystem |
| Data wrangling | pandas, numpy | Already used in `build_features.py` |
| Analytical builds | DuckDB + parquet (optional) | Fast local feature builds without a DB round-trip |
| ML models | LightGBM (primary), scikit-learn pipelines | Tabular, small data, fast, SHAP TreeExplainer support |
| Calibration | `sklearn` isotonic / Platt via `CalibratedClassifierCV` | FR-3 calibrated probabilities |
| Explainability | `shap` (TreeExplainer) | Native GBDT support, fast |
| API framework | FastAPI + Pydantic v2, Uvicorn/Gunicorn | Async, typed, OpenAPI for free |
| Datastore | PostgreSQL 15 (SQLAlchemy 2.0 + Alembic) | Relational schema in BACKEND_SCHEMA.md |
| Cache / rate limit / jobs | Redis + RQ (or Celery) | Prediction cache, quota counters, scrape jobs |
| Object storage | S3-compatible (raw JSON, model artifacts) | Durable, cheap, versioned |
| Frontend | Next.js 14 (App Router), TypeScript, React 18 | SSR for SEO on profile pages; mature ecosystem |
| UI kit | Tailwind CSS + shadcn/ui | Fast, consistent, themable |
| Charts | visx / Recharts + custom SVG | Heatmap + field diagram need custom SVG |
| Data fetching | TanStack Query | Cache, retries, background refresh |
| Auth (users) | Auth.js (NextAuth) or Clerk | Email + Google; sessions |
| Auth (API) | API keys (hashed), scoped to plan | Programmatic tier |
| Billing | Stripe (subscriptions + metered usage) | Standard, supports both models |
| CI/CD | GitHub Actions | Tests, lint, scheduled scrape, deploy |
| Containerization | Docker (multi-stage) | Reproducible deploys |
| Hosting | Fly.io / Railway / Render (v1); AWS ECS (scale) | Small ops footprint early |
| Error tracking | Sentry | Backend + frontend |
| Metrics / tracing | OpenTelemetry → Grafana Cloud / Prometheus | Latency budgets, model timings |

Dependency policy: pin in `requirements.txt` / `package.json`; no new runtime
dependency without a note in the PR describing why the stdlib / existing dep
is insufficient (see [RULES.md](RULES.md)).

## 3. Data pipeline requirements

### 3.1 Scraper (`scripts/scraper.py` — exists)

- **DR-1** MUST be idempotent: a match already on disk / in the raw store is
  not re-fetched.
- **DR-2** MUST be polite: ≥ 2.5 s between page requests, ≥ 5 s between
  matches, a longer pause every N matches. Configurable.
- **DR-3** MUST persist one combined JSON per match with `match_id`,
  `series_id`, `meta`, `comments[]`.
- **DR-4** MUST retry transient failures with exponential backoff and raise a
  typed `ScrapeError` after `max_retries`; a single match failure MUST NOT
  abort the batch.
- **DR-5** MUST tolerate the endpoint 403ing from some networks; document and
  detect (extraction-quality + HTTP status logging), do not silently write
  empty files.
- **DR-6 (new)** Prod MUST write raw JSON to object storage as well as (or
  instead of) local disk, keyed `raw/{series_id}/{match_id}.json`.
- **DR-7 (new)** A scheduled GitHub Actions workflow runs the scraper daily
  with a small `--batch-size`; failures open an alert, not a red build only.

### 3.2 Parser (`scripts/nlp_parser.py` — exists)

- **DR-8** MUST access unofficial fields defensively (multiple candidate
  keys, never a hard failure on a missing key).
- **DR-9** Length / line / shot / dismissal extraction MUST be deterministic:
  ordered phrase dictionaries, most-specific category first.
- **DR-10** MUST log per-field extraction rate (`ball_length`, `ball_line`,
  `shot_type`, `dismissal_type`). CI/monitoring MUST fail/alert if any field
  drops below a configured floor on a known-good fixture set.
- **DR-11** Output schema (`deliveries`): `match_id, innings, over,
  ball_in_over, batsman, bowler, text, total_runs, ball_length, ball_line,
  shot_type, outcome, is_wicket, dismissal_type, player_out`.
- **DR-12** Prefer reliable numeric fields (`totalRuns`, `isWicket`) over
  phrase matching for `outcome`; use the full commentary sentence, not
  terse scorecard shorthand, for `dismissal_type`.

### 3.3 Feature builder (`scripts/build_features.py` — exists)

- **DR-13 (leakage)** Every feature for row *r* MUST be computable strictly
  before ball *r*. Rolling stats use `groupby(...).transform(cumsum → shift(1))`
  scoped inside the same group (never a chained `.shift(1)` after `cumsum()`).
- **DR-14 (leakage)** Historical/vulnerability features for row *r* MUST be
  aggregated over every match **except** row *r*'s own match
  (`other = total − this_match`, floored at 0).
- **DR-15** Feature set (current): `phase`, `phase_encoded`,
  batsman rolling (`runs_so_far`, `balls_faced`, `strike_rate`, `dot_pct`),
  bowler rolling (`balls_bowled`, `wickets_so_far`, `economy`),
  match context (`innings_score`, `innings_wickets`, `pressure_index`),
  historical batsman (`hist_dismissal_type_*_pct`, `hist_ball_length_*_pct`,
  `hist_ball_line_*_pct`, `hist_phase_avg`, `hist_avg_under_pressure`,
  `hist_avg_normal`), encodings (`ball_length_encoded`, `ball_line_encoded`),
  targets (`will_dismiss`, `dismissal_type_encoded`).
- **DR-16** Documented simplifications MUST stay documented in the module
  docstring: `total_runs` treated as runs off the bat; bowler "spell" ==
  cumulative per (match, innings, bowler).
- **DR-17** Output MUST be deterministic given identical `deliveries.csv`
  (stable sort by `match_id, innings, over, ball_in_over`).
- **DR-18 (new)** A `tests/leakage/` suite asserts, on synthetic data, that
  shuffling or nulling the outcome of row *r* does not change row *r*'s
  feature vector.

### 3.4 Match-ID resolver (`scripts/match_ids.py` — exists)

- **DR-19** MUST try the series-schedule API first, fall back to
  `data/match_ids_manual.json`, de-duplicate preserving order.
- **DR-20** A missing manual file is not an error (fresh checkout).

## 4. Model requirements

### 4.1 Models

| ID | Model | Type | Input | Output |
| --- | --- | --- | --- | --- |
| M1 | Dismissal probability | Binary classifier + calibration | situation features + candidate `(length, line, bowler_type)` | `P(wicket)` ∈ [0,1] |
| M2 | Dismissal type | Multiclass (6) | same, conditioned on wicket | dist over `{caught, bowled, lbw, run_out, stumped, hit_wicket}` |
| M3 | Expected runs | Regressor (or ordinal) | same | `E[runs]` for the ball |
| M4 | Recommendation engine | Ranker over candidates | situation | ranked list of candidate deliveries |
| M5 | Field placement | Heuristic (v1) → model (v2) | recommended `(length,line)` + batsman scoring zones | field preset + positions |

M4 is not a learned model in v1: it enumerates the candidate grid
(`BALL_LENGTHS × BALL_LINES × BOWLER_TYPES`, ~175 combos), scores each with
M1/M3, and ranks by an objective:
`score = w1 · P(wicket) − w2 · normalized(E[runs]) − w3 · low_sample_penalty`.
Weights are configurable per phase (wicket-weighted at the death differs from
the middle overs).

### 4.2 Training and evaluation

- **MR-1** Cross-validation MUST be **grouped by `match_id`** (a match is
  never split across train/test). Prefer leave-one-tournament-out for the
  headline number.
- **MR-2** Report for M1: Brier score, log loss, ROC-AUC, PR-AUC, and a
  reliability curve; compare against a base-rate and a "phase base-rate"
  baseline. Acceptance: Brier ≥ 15% better than base rate (PRD §9).
- **MR-3** Report for M2: macro-F1, per-class precision/recall, confusion
  matrix. Acceptance: macro-F1 ≥ 0.45.
- **MR-4** Report for M3: MAE, RMSE, calibration of `E[runs]` vs realized.
- **MR-5** Recommendation backtest: on held-out balls, bucket by the model's
  top recommendation vs the delivery actually bowled; report realized wicket
  rate and runs per ball per bucket ("uplift"). This is the product metric.
- **MR-6** Every training run writes an eval report (JSON + markdown) and the
  fitted artifact to the model registry with: git SHA, data snapshot hash,
  feature list, hyperparameters, metrics.
- **MR-7** Models MUST expose a **confidence / low-sample flag** when the
  batsman's historical row count is below a threshold.
- **MR-8** SHAP `TreeExplainer` values MUST be producible for any single
  prediction in < 50 ms; background dataset is a fixed sample stored with the
  artifact.

### 4.3 Model lifecycle

- Artifacts: `models/{model_id}/{version}/model.pkl`, `meta.json`,
  `eval.md`, `shap_background.parquet`. Version = ISO date + short SHA.
- Registry: a `models` table (see BACKEND_SCHEMA.md) records which version is
  `active` per model_id and environment.
- Rollout: new version deployed as `candidate`; promote to `active` after the
  eval report passes gates; API loads `active` at boot and on a refresh
  signal. Rollback = flip the pointer.
- No online learning in v1.

## 5. API requirements

### 5.1 General

- **AR-1** REST, JSON, versioned under `/v1`. OpenAPI schema published at
  `/v1/openapi.json`; interactive docs at `/docs`.
- **AR-2** Auth: `Authorization: Bearer <api_key>` for programmatic;
  session cookie for the console's own calls (same backend, separate
  dependency).
- **AR-3** Every response includes `X-Request-Id`; errors follow a single
  envelope `{ "error": { "code", "message", "details"? } }`.
- **AR-4** Rate limiting and quota per API key / plan, enforced in
  middleware backed by Redis; `429` with `Retry-After` and
  `X-RateLimit-*` headers.
- **AR-5** p95 latency budget for `POST /v1/recommendation`: 500 ms with warm
  model and cached batsman features; 1500 ms cold.
- **AR-6** Idempotent GETs are cacheable (`Cache-Control`, `ETag`).
  Recommendations for an identical situation payload are cached in Redis for
  a short TTL keyed by `hash(payload) + model_version`.

### 5.2 Endpoints (v1)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/recommendation` | Core: situation → ranked deliveries + reasons |
| `POST` | `/v1/predict/dismissal` | Just M1/M2 for a fully-specified delivery |
| `GET` | `/v1/batsmen` | Search / list batsmen in the dataset |
| `GET` | `/v1/batsmen/{id}/profile` | Vulnerability profile (FR-5) |
| `GET` | `/v1/matches` | Browse matches in the dataset |
| `GET` | `/v1/matches/{id}/timeline` | Ball-by-ball for the match browser |
| `GET` | `/v1/reference` | Enum vocab (phases, lengths, lines, bowler types) |
| `POST` | `/v1/scenarios` / `GET` `/v1/scenarios` | Save / list scenarios (auth) |
| `GET` | `/v1/usage` | Caller's current period usage vs quota |
| `GET` | `/healthz`, `/readyz` | Liveness / readiness |

### 5.3 Core request/response shape

```jsonc
// POST /v1/recommendation
{
  "match": { "innings": 2, "over": 43, "ball_in_over": 2,
             "score": 271, "wickets": 6, "target": 322 },
  "batsman_id": "player_1234",
  "bowler_type": "pace_right_arm",
  "options": { "top_k": 3, "objective": "death" }
}
```

```jsonc
{
  "model_version": "2026-08-01.a1b2c3d",
  "situation": { "phase": "death", "pressure_index": 7.4, "low_sample": false },
  "recommendations": [
    {
      "rank": 1,
      "length": "yorker", "line": "off_stump",
      "dismissal_probability": 0.081,
      "dismissal_type_top": "bowled",
      "expected_runs": 1.1,
      "field_preset": "death_yorker_ring",
      "field_positions": ["...", "..."],
      "reasons": [
        "This batsman is bowled on 34% of his dismissals vs 21% dataset average.",
        "Averages 12.4 at the death vs 41 in the middle overs.",
        "Under pressure (index 7.4) his dot% rises and SR drops."
      ],
      "confidence": "medium"
    }
    // ... rank 2, 3
  ]
}
```

### 5.4 Errors

`400` invalid situation (out-of-range over, unknown enum) · `401` bad key ·
`402` plan required · `404` unknown batsman/match · `422` well-formed but
unusable (e.g. batsman with zero history) · `429` quota/rate ·
`503` model not loaded.

## 6. Frontend requirements

- **FE-1** Next.js App Router; batsman profile and match pages are
  server-rendered and indexable; the strategy console is a client app.
- **FE-2** All data via the same `/v1` API (no private backchannel) so the
  API stays dogfooded.
- **FE-3** The console MUST render the length × line heatmap and the field
  diagram as inline SVG, theme-aware (light/dark), and printable.
- **FE-4** Every recommendation card MUST show the reasons and a confidence
  badge; a "low sample" state is visually distinct.
- **FE-5** WCAG 2.1 AA: keyboard navigation for the situation builder, color
  is never the only signal on the heatmap, focus states visible.
- **FE-6** Offline-tolerant: a dropped API call shows a retry, never a blank
  card (TanStack Query retry + error boundary).
- See [DESIGN.md](DESIGN.md) and [UI_WORKFLOW.md](UI_WORKFLOW.md).

## 7. Recommendation-quality backtest (product metric)

Held-out matches only. For each ball:

1. Build the candidate grid, score with M1/M3, take the model's top-1.
2. Compare to the delivery actually bowled (as parsed).
3. Aggregate realized `is_wicket` and `total_runs` for balls where
   model-top-1 == actual vs where it differs.

Report the **uplift**: realized wicket rate on "matched" balls minus overall,
and runs/ball delta. A positive, stable uplift across tournaments is the gate
for calling M4 shippable. This is an observational proxy (we cannot
counterfactually bowl the recommended ball), stated as such in the UI.

## 8. Observability

- Structured logs (JSON) from every service; the existing `app/utils/logger`
  is the base — extend with request id + model version fields.
- Metrics: request rate / latency / error rate per endpoint; model inference
  time; SHAP time; cache hit rate; scrape success rate; extraction-quality
  gauges.
- Traces: `recommendation` request → feature fetch → M1 → M3 → rank → SHAP.
- Alerts: scrape failure 2 days running; extraction quality below floor;
  p95 latency breach; 5xx rate > 1%; model registry has no `active` version.

## 9. Security and compliance

- API keys stored hashed (Argon2/bcrypt); shown once on creation.
- Secrets via environment / secret manager; never committed;
  `.env` gitignored (already).
- Postgres least-privilege roles: pipeline writes, API reads a view.
- Raw scraped commentary is **not** redistributed via the API; only derived
  aggregates and predictions are exposed. Legal review before public launch
  (see PRD §11).
- PII limited to account email + billing metadata (held by Stripe). GDPR
  delete = remove user row + API keys + scenarios; cricket data has no PII.
- Standard headers (HSTS, CSP, X-Content-Type-Options) on the web app.

## 10. Testing requirements

| Suite | Scope | Runs |
| --- | --- | --- |
| `tests/scripts/` (exists) | scraper / parser / features / match_ids, offline synthetic | every CI run |
| `tests/leakage/` (new) | asserts no feature uses row-local outcome; historical excludes own match | every CI run |
| `tests/models/` (new) | training smoke on a tiny fixture; eval report schema; SHAP produces values | every CI run |
| `tests/api/` (new) | endpoint contract tests against FastAPI TestClient; auth, quota, error envelopes | every CI run |
| `tests/e2e/` (new) | Playwright: situation builder → recommendation renders → reasons visible | pre-deploy |
| Extraction-quality gate | parser run on committed golden fixtures, per-field floor | every CI run |

All Python tests offline (no network, no scraped data required) — this is an
existing invariant, keep it.

## 11. Performance budgets

| Operation | Budget |
| --- | --- |
| Feature build, 1 tournament (~50 matches, ~30k balls) | < 60 s on a laptop |
| M1 single inference | < 5 ms |
| Candidate grid scoring (175 combos) | < 40 ms |
| SHAP for one recommendation | < 50 ms |
| `POST /v1/recommendation` end-to-end p95 (warm) | < 500 ms |
| Console first contentful paint | < 1.5 s on broadband |

## 12. Deployment

- One Docker image for the API; migrations run as an init step (Alembic).
- Frontend deployed separately (Vercel or a Node container).
- Model artifacts pulled from object storage at boot; version pinned by
  env var or the `models` table pointer.
- Zero-downtime: rolling deploy; `/readyz` gates traffic until model loaded.
- Scheduled scrape is a separate cron job / GitHub Action, not in the API
  container.

## 13. Traceability

Each PRD functional requirement maps to a TRD section:
FR-1/2/3/4 → §4, §5.3 · FR-5 → §5.2 (`/batsmen/{id}/profile`) · FR-6 → §5.2
(`/scenarios`) · FR-7 → §5.1 (AR-2, AR-4) · FR-8 → §3 · FR-9 → §3.3
(DR-13/14/18).
