# CricXAI — Delivery Phases

Status: Draft v1 · Last updated: 2026-08-28

Each phase has a goal, deliverables, and an **exit gate** — objective
criteria that must be true before the next phase starts. Phases can overlap
at the edges but a gate is a gate.

---

## Phase 0 — Foundations (DONE)

**Goal:** reproducible data pipeline from raw commentary to a leakage-free
feature table.

Deliverables: `match_ids.py`, `scraper.py`, `nlp_parser.py`,
`build_features.py`, shared `app/utils/`, offline test suite, README runbook.

**Exit gate:** ✅ `python -m pytest tests/` green; a raw match JSON runs end
to end to `delivery_features.csv`.

---

## Phase 1 — Mock data + model + serving skeleton (CURRENT)

**Goal:** a working vertical slice on synthetic data — you can ask for a
recommendation and get a ranked, explained answer, in a UI.

Deliverables:
- `scripts/mock_data.py` — 10 probable-2027-World-Cup squads, deterministic
  ODI simulator, 100 matches → `deliveries.csv` + `matches.csv`
  (`source=mock`, `series_id=MOCK`).
- Feature table built from mock data.
- `scripts/train.py` — M1 dismissal probability (calibrated), M2 dismissal
  type, M3 expected runs; grouped CV; eval report; artifacts in
  `data/models/` + `active.json`.
- `app/engine/` — candidate-grid recommendation ranker + reason templates.
- `app/api/` — FastAPI `/v1`: `/recommendation`, `/predict/dismissal`,
  `/batsmen`, `/batsmen/{id}/profile`, `/matches`, `/reference`, `/healthz`.
- `web/` — Next.js strategy console (situation builder, ranked cards,
  length×line heatmap, field diagram, reasons), batsman profile,
  match browser. Design per DESIGN.md (clean, minimalist).
- `deploy/` — Dockerfile, docker-compose (api + web + postgres + redis),
  GitHub Actions CI, one-command deploy config (render.yaml / fly.toml).

**Exit gate:**
- `make demo` regenerates data → features → models → serves API → console
  renders a recommendation with reasons.
- M1 beats base-rate Brier by ≥ 10% on grouped CV **on mock data** (sanity,
  not the real bar).
- API contract tests (`tests/api/`) and leakage tests green in CI.
- Container image builds; `docker compose up` brings the whole stack up.
- Preview deployment reachable.

---

## Phase 2 — Real data ingestion

**Goal:** replace mock with scraped ODI data for a first real tournament.

Deliverables: series IDs filled in `TOURNAMENTS`; scheduled scrape
(GitHub Action, small batches, alerting); extraction-quality dashboard;
player name-resolution table; golden fixtures for the quality gate;
re-run features + models on real data; "low sample" flag wired through API
and UI.

**Exit gate:**
- ≥ 1 full tournament scraped, parsed, extraction quality above floor on all
  four fields.
- Models retrained on real data; M1 Brier ≥ 15% better than base rate,
  reliability curve within ±0.03 of diagonal in the 0–0.2 band (PRD §9).
- Recommendation backtest (TRD §7) shows non-negative uplift on held-out
  matches.
- Legal sign-off on using scraped data for internal modeling.

---

## Phase 3 — Persistence & platform

**Goal:** move off CSVs; make the service production-shaped.

Deliverables: Postgres schema + Alembic migrations (BACKEND_SCHEMA.md);
`scripts/load_db.py` (CSV → tables); `models` registry table + promote/
rollback; Redis prediction cache + quota counters; object storage for raw
JSON and artifacts; structured logs with request id + model version;
Sentry + metrics + latency dashboards + alerts.

**Exit gate:**
- API reads features and models from Postgres/object storage, not local CSV.
- p95 `/v1/recommendation` < 500 ms warm (TRD §11).
- Model promote and rollback are a pointer flip, verified in staging.
- Dashboards live; alerts fire in a drill.

---

## Phase 4 — Explanations & model quality

**Goal:** make recommendations trustworthy and the reasons genuinely useful.

Deliverables: SHAP endpoint hardened (< 50 ms, stored background set);
cricket-language reason templates reviewed by a domain expert; confidence
calibration surfaced in UI; field-placement model (shot-direction
distribution → field), replacing the v1 heuristic; a small trained text
classifier for `ball_length`/`ball_line` as a fallback to phrase matching;
model card per model.

**Exit gate:**
- Every recommendation carries 3–6 reasons; expert review rates ≥ 80% as
  "accurate and useful".
- Dismissal-type macro-F1 ≥ 0.45; expected-runs MAE reported and stable.
- Field model beats the heuristic on a held-out shot-direction metric.

---

## Phase 5 — Monetization

**Goal:** paid product.

Deliverables: Auth.js/Clerk auth (email + Google); API key management
(hashed, scoped); plans + Stripe subscriptions + metered usage; quota
enforcement at gateway and console; usage dashboard; billing reconciliation
job; pricing page; docs site for the API + generated SDK.

**Exit gate:**
- A user can sign up, hit the free limit, upgrade via Stripe, and see quota
  reset — end to end in staging.
- Metered usage reconciles with Stripe within 1% in a 7-day test.
- API docs published; SDK installs and makes a call.

---

## Phase 6 — Scale & breadth

**Goal:** more formats, more users, teams.

Candidates: T20 and Test support (new phase/vocab handling, format-specific
models); team/org accounts with seats and roles; bulk export + async report
jobs; live match feed integration (licensed); mobile-optimized console;
warehouse for analytical feature builds; per-region API.

**Exit gate:** defined at Phase 5 close based on demand.

---

## Cross-cutting, every phase

- Leakage tests and extraction-quality gate stay green (RULES.md).
- Docs in `docs/` updated in the same PR as the change they describe.
- `docs/MEMORY.md` decision log appended when a non-obvious call is made.
