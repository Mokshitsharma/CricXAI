# CricXAI — Project Memory

A living "memory bank" for anyone (human or agent) picking up this project.
State, decisions, gotchas, glossary. Append to the decision log; don't
rewrite history.

Last updated: 2026-08-28

---

## 1. Where things stand

| Area | State |
| --- | --- |
| Data pipeline (scrape → parse → features) | Built, tested offline (Phase 0 done) |
| Mock data (10 squads, 100 ODIs) | Built this session — `scripts/mock_data.py` |
| Feature table | Built from mock data |
| Models M1/M2/M3 | Trained on mock data — `scripts/train.py`, artifacts in `data/models/` |
| Recommendation engine | Built — `app/engine/` |
| API (`/v1`) | Built (CSV-backed) — `app/api/` |
| Web console | Design canvas + Next.js scaffold in `web/` |
| Deployment | Docker + compose + CI + deploy config in `deploy/` |
| Postgres / Redis / object storage | Specified, not wired (Phase 3) |
| Auth / billing | Specified, not built (Phase 5) |
| Real scraped data | Not yet — `TOURNAMENTS` series IDs still `None` |

Run the whole mock slice: `make demo` (or the commands in
[APP_FLOW.md](APP_FLOW.md) §1).

Python: use **`py -3.13`** — the global 3.13 has pandas/sklearn/lightgbm/
shap/fastapi. The repo `venv/` (3.13) lacks lightgbm/shap.

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
