# CricXAI — Project Memory

A living "memory bank" for anyone (human or agent) picking up this project.
State, decisions, gotchas, glossary. Append to the decision log; don't
rewrite history.

Last updated: 2026-08-28

---

## 1. Where things stand

| Area | State |
| --- | --- |
| Data pipeline (ingest/parse → features) | Built, tested offline (Phase 0 done) |
| Mock data (10 squads, 100 ODIs) | `scripts/mock_data.py` — tests/CI + offline dev only |
| Feature table | Built from **real Cricsheet data** (`make real`); mock path still works |
| Models M1/M2/M3 | Active artifacts trained on **real data** (`data_source: mixed/real`) — `scripts/train.py` |
| Recommendation engine | Built — `app/engine/` (length×line grid is flat on real data, see Cricsheet decision) |
| API (`/v1`) | Built (CSV-backed) — `app/api/`; adds teams / matchup / team-squad / team-matchup |
| Web console | Single-file `app/api/static/`; Console + PvP + Matchup/XI wired to `/v1`; Dossier/Rosters/Stadium still demo data. `web/` = design canvas only, no Next.js app yet |
| Deployment | Docker + compose + CI + deploy config in `deploy/` |
| Postgres / Redis / object storage | Specified, not wired (Phase 3) |
| Auth / billing | Specified, not built (Phase 5) |
| Real ESPN scraped data | Not pursued — `TOURNAMENTS` series IDs still `None` |
| Real Cricsheet data | Ingested (Phase 2) — `scripts/cricsheet_ingest.py`, 2,569 male ODIs / 1.36M deliveries, `source="cricsheet"`. **No length/line/shot** in the source (`"unknown"`). |

Run on real data: `make real` (cricsheet_ingest → features → train, ~15 min).
Run the mock slice: `make models` / `make demo` (or [APP_FLOW.md](APP_FLOW.md) §1).

Python: `venv/` now has lightgbm 4.7 + shap 0.52 installed (was missing
them); `pip install -r requirements.txt` covers everything. Global 3.13
also works.

## 2. Decision log

- **2026-08-28 — Doc set created.** PRD/TRD/architecture/design/UI/app-flow/
  schema/rules/phases/impl-plan/this file, all in `docs/`. Grounded in the
  existing Phase 0 code.
- **2026-08-28 — Mock data before live scraping (ADR-003).** The
  ESPNcricinfo endpoint 403s from some networks and the legal posture for
  scale isn't settled. A deterministic simulator for 10 probable-2027
  World Cup squads over 100 ODIs unblocks models + API + UI now. Mock rows:
  `source="mock"`, `series_id="MOCK"`. Never train a "real" model on them
  without an explicit `--allow-mixed` flag.
- **2026-08-28 — Simulator emits the parser's output schema directly.**
  Generating realistic commentary prose to feed `nlp_parser.py` isn't worth
  it; `mock_data.py` writes `deliveries.csv` / `matches.csv` in the exact
  columns `nlp_parser.py` produces, so `build_features.py` runs unchanged.
- **2026-08-28 — LightGBM + isotonic calibration for M1** (ADR-001/006).
  Small tabular data, need calibrated probabilities and fast SHAP.
- **2026-08-28 — Recommendation is a scored candidate grid, not a learned
  policy** (ADR-004). ~35 length×line cells per bowler type; score with
  M1/M3; rank by a phase-weighted objective. Interpretable, no
  counterfactual data needed.
- **2026-08-28 — Single public `/v1` API, dogfooded by the console**
  (ADR-005). No private endpoints for core features.
- **2026-08-28 — CSV-backed data access layer now, Postgres later.**
  `app/api/data.py` loads CSVs into memory at boot behind an interface that
  a DB implementation will replace in Phase 3.
- **2026-08-30 — Real data source is Cricsheet, not ESPN scraping
  (supersedes ADR-003's "mock until scraping").** Cricsheet publishes
  ball-by-ball ODI JSON under ODC-BY (attribution, derivatives OK) — no
  403s, no scraping fragility, defensible licence. `scripts/cricsheet_ingest.py`
  reads `data/external/cricsheet/odis_json.zip` and writes the parser's
  schema directly (`source="cricsheet"`). ESPN `scraper.py`/`nlp_parser.py`
  kept only as the future path to real length/line.
- **2026-08-30 — Cricsheet has NO ball length / line / shot type.** They
  ingest as `"unknown"`. Consequence: M1/M3 lose all length×line signal, so
  the candidate-grid recommender (M4) returns near-flat scores across cells
  on Cricsheet-only models. The dismissal-risk / dismissal-type / expected-
  runs numbers are real; the *prescribe length & line* headline needs either
  a labelled heuristic layer or a separate real length/line feed (Phase 4 /
  open question). Afghanistan men's matches are withheld by Cricsheet.
- **2026-08-30 — `train.py` `source` label.** With Cricsheet rows the
  repo's `data/models/` artifacts are tagged `data_source="mixed/real"`
  (the code only special-cases an all-`mock` frame). Tests are unaffected —
  the `trained_env` fixture trains its own tiny mock set in a temp dir; only
  `test_dismissal_prob_full_dataset_quality_if_present` reads the repo's
  active model (needs `roc_auc >= 0.65`).

## 3. Gotchas / landmines

- **groupby + chained shift is a leakage trap.** `df.groupby(k).cumsum()`
  then a chained `.shift(1)` crosses group boundaries. Always
  `.transform(lambda s: s.cumsum().shift(1).fillna(0))`. Comment is in
  `build_features.py`; rule R-2 in [RULES.md](RULES.md).
- **Historical features must exclude the row's own match** (`other = total −
  this_match`, floored at 0). Rule R-3.
- **ESPN commentary endpoint is unofficial** and 403s from sandboxed / some
  IP ranges — even the homepage was blocked during dev. If scraping "fails
  everywhere", verify from a residential browser before assuming the code
  broke. Field names are undocumented → `nlp_parser.py` reads defensively.
- **Phrase dictionaries are order-sensitive** — most-specific category
  first (`wide_outside_off` before `outside_off`). Adding a phrase needs a
  test.
- **`total_runs` is treated as runs off the bat** in `build_features.py`
  (byes/leg-byes not separated yet). Documented in the module docstring;
  don't "fix" silently.
- **Bowler "spell" == cumulative per (match, innings, bowler)** — real spell
  boundaries aren't parsed.
- **Some `hist_ball_length_*` / `hist_ball_line_*` columns are
  data-dependent** (built from categories present in wicket rows). The exact
  trained feature list is persisted in each model's `meta.json` and
  re-validated at serve time (R-15).
- **Mock skills are illustrative**, not scouting data — don't surface them
  as real ratings (R-18).
- Base branch is `main`; current working branch is `master`.

## 4. Glossary

| Term | Meaning |
| --- | --- |
| Phase | ODI over-band: powerplay (0–9), early_middle (10–19), middle (20–29), late_middle (30–39), death (40–49). `phase_from_over()` in `cricket_constants.py`. |
| Length | yorker · full · good · short · bouncer |
| Line | wide_outside_off · outside_off · off_stump · middle_stump · leg_stump · down_leg · wide_down_leg |
| Dismissal type | caught · bowled · lbw · run_out · stumped · hit_wicket |
| Bowler type | pace_right_arm · pace_left_arm · off_spin · leg_spin · left_arm_spin |
| pressure_index | Chasing-only scalar: (required RR − current RR) + wickets-down weight, capped at 10. 0 for the team batting first. |
| M1 / M2 / M3 | Dismissal probability / dismissal type / expected runs models. |
| M4 | The recommendation engine (grid scoring + ranking), not a learned model in v1. |
| Uplift | Recommendation backtest metric: realized wicket rate on balls where model top-1 == ball actually bowled, vs overall (TRD §7). |
| Low sample | Batsman has too few historical dismissals for a confident profile; flagged in API + UI. |

## 5. Open questions (carry forward)

- License a commercial ball-by-ball feed before public launch, or ship on
  scraped data with a disclaimer? (PRD §13)
- Minimum matches per tournament before a batsman profile shows without a
  "low sample" warning?
- Field placement: keep the heuristic for v1, or build a shot-direction
  model first? (Phase 4)
- Objective weights per phase — tune on the backtest once real data exists.

## 6. Pointers

- Runbook: `docs/README.md`, [APP_FLOW.md](APP_FLOW.md) §1.
- What each module does: [ARCHITECTURE.md](ARCHITECTURE.md) §2 and §5.
- Rules that CI enforces: [RULES.md](RULES.md) §1, §2, §8.
- What's next: [PHASES.md](PHASES.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
