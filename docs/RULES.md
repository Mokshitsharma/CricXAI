# CricXAI — Engineering Rules & Conventions

Status: Living document · Last updated: 2026-08-28

These are enforced in review and, where marked, in CI. If a rule blocks
something genuinely necessary, change the rule in a PR — don't quietly break it.

---

## 1. Data leakage (non-negotiable)

- **R-1** A feature for ball *r* MUST be computable from information available
  strictly **before** ball *r* is bowled.
- **R-2** Rolling "so far this innings/spell" stats MUST shift inside the
  group:
  `series.groupby(keys).transform(lambda s: s.cumsum().shift(1).fillna(0))`.
  A `.groupby(...).cumsum()` followed by a **chained** `.shift(1)` is banned
  — the chained shift crosses group boundaries and pulls the previous
  group's last value. (Comment already in `build_features.py`.)
- **R-3** Historical / vulnerability aggregates for ball *r* MUST exclude
  ball *r*'s own match: `other = total − this_match`, floored at 0. Never a
  plain "all matches including this one" average.
- **R-4** Targets (`will_dismiss`, `dismissal_type_encoded`) and anything
  derived from the current ball's outcome are NEVER inputs.
- **R-5** CV splits are **grouped by `match_id`**. The headline metric uses
  leave-one-tournament-out. Random k-fold is banned for reported numbers.
- **R-6 (CI)** `tests/leakage/` must pass: perturbing row *r*'s outcome
  leaves row *r*'s feature vector byte-identical; historical columns for a
  single-match dataset are all zero.

## 2. Parsing the unofficial APIs

- **R-7** Never assume a field name. Read via helpers that try multiple
  candidate keys and return `None`/default on miss (`_get_first`,
  `_get_nested_name`, `_get_commentary_text` patterns).
- **R-8** A missing field is a warning + default, never an exception that
  aborts a batch. One bad match must not stop the run.
- **R-9** Phrase dictionaries are **ordered, most-specific first**
  (`wide_outside_off` before `outside_off`). Matching is first-hit wins and
  MUST be deterministic. Adding a phrase requires a test case.
- **R-10** Prefer reliable structured fields over prose: use `totalRuns` /
  `isWicket` for `outcome`; use the full commentary sentence (not terse
  `dismissal_text`) for `dismissal_type`.
- **R-11 (CI)** The extraction-quality gate runs the parser on committed
  golden fixtures; each of `ball_length`, `ball_line`, `shot_type`,
  `dismissal_type` must stay above its configured floor.

## 3. Determinism & reproducibility

- **R-12** `build_features.py` output MUST be deterministic for identical
  input — stable sort on `(match_id, innings, over, ball_in_over)`.
- **R-13** Any simulator / sampling code (`mock_data.py`, training splits)
  takes an explicit `--seed` and defaults it to a constant.
- **R-14** Training writes `meta.json` with git SHA, data snapshot hash,
  ordered feature list, hyperparameters, and metrics. No artifact without
  metadata.
- **R-15** The exact feature column list (some `hist_*` columns are
  data-dependent) is persisted with the model and re-validated at serve time.

## 4. Mock vs real data

- **R-16** Mock rows carry `source = "mock"` and `series_id = "MOCK"`.
- **R-17** A training or eval run that mixes `mock` and real rows MUST pass
  `--allow-mixed` explicitly and stamp it in `meta.json`.
- **R-18** Mock squads/skills are illustrative, not scouting data. Don't
  present them in the UI as real player ratings.

## 5. Module boundaries

- **R-19** `app/utils/` has no dependency on `scripts/`, `app/engine/`, or
  `app/api/`. `cricket_constants.py` is the single source of the vocab and
  encodings — the parser, feature builder, engine and API all import from it,
  never redefine.
- **R-20** `app/engine/` (recommendation) is framework-free: no FastAPI, no
  DB imports. It takes feature vectors and models in, returns ranked
  results. This keeps it unit-testable and reusable from a notebook.
- **R-21** `app/api/` owns HTTP, auth, quota, serialization only. Business
  logic lives in `engine/` and `ml/`.
- **R-22** DB access goes through `app/db/`; no raw SQL scattered in routers.

## 6. Python style

- **R-23** `from __future__ import annotations` at the top of every module
  (matches existing code).
- **R-24** Type-hint public functions. Module + public-function docstrings
  explaining *why*, not just *what* (see existing modules for the bar).
- **R-25** Prefer stdlib + already-present deps. A new runtime dependency
  needs a sentence in the PR on why existing tools don't suffice.
- **R-26** `pathlib.Path`, not string paths. IO through `app/utils/file_io`.
- **R-27** Logging through `app/utils/logger.get_logger(__name__)` — never
  `print` in library code (CLIs may `print` their final result).
- **R-28** Line length 100. Formatter: `ruff format`. Linter: `ruff`.

## 7. Frontend style

- **R-29** TypeScript strict. No `any` without a `// reason:` comment.
- **R-30** All server data through the typed `/v1` client generated from the
  OpenAPI schema; no ad-hoc `fetch` to undocumented paths.
- **R-31** Components are theme-aware (light/dark) via CSS variables; color
  is never the only signal (heatmap, confidence).
- **R-32** Every async view has explicit loading, empty, error, and
  low-sample states. No spinner-forever, no blank card.
- **R-33** Accessibility: keyboard path through the situation builder;
  visible focus; `aria` labels on the SVG heatmap/field cells.

## 8. Testing

- **R-34** Python tests run **offline** — no network, no real scraped data.
  Synthetic fixtures only. (Existing invariant.)
- **R-35** New parser phrases, new features, new endpoints each land with
  tests in the same PR.
- **R-36** `tests/leakage/`, `tests/models/` (training smoke + eval schema),
  `tests/api/` (contract + auth + quota + error envelope) all run in CI.
- **R-37** A bug fix starts with a failing test that reproduces it.

## 9. Security & secrets

- **R-38** No secrets in the repo. `.env` is gitignored; use
  `.env.example` for shape. Prod uses a secret manager.
- **R-39** API keys stored hashed; the plaintext is shown once at creation.
- **R-40** The API never returns raw scraped commentary in bulk — only
  derived aggregates and predictions (legal posture, PRD §11).
- **R-41** Dependency updates reviewed; `pip-audit` / `npm audit` in CI.

## 10. Scraping etiquette

- **R-42** Keep the polite defaults: ≥ 2.5 s between requests, ≥ 5 s between
  matches, longer pause every N. Don't lower them for a "quick" backfill.
- **R-43** Idempotent — never re-fetch a match already stored.
- **R-44** Identify honestly in the `User-Agent`. Back off on `429`/`5xx`
  with exponential delay; abort the match after `max_retries`, not the batch.

## 11. Git & PRs

- **R-45** Work on a branch; open a PR into `main`. No direct pushes to
  `main`/`master`.
- **R-46** One logical change per PR. Pipeline change + schema change +
  model change = separate PRs where possible.
- **R-47** PR description states: what, why, leakage impact (if any feature
  touched), and test additions.
- **R-48** Commits and PRs carry no AI-assistant attribution — no
  `Co-Authored-By` / tool trailers, no "generated with" lines. Commit under
  your own name and email.
- **R-49** CI green (tests + lint + leakage + extraction-quality) before
  merge.

## 12. PR review checklist (paste into the PR)

```
- [ ] No feature uses post-ball info (R-1..R-4)
- [ ] Rolling stats shift inside the group (R-2)
- [ ] Historical aggregates exclude the row's own match (R-3)
- [ ] CV grouped by match (R-5) if models touched
- [ ] New parser phrases have tests and keep dictionaries ordered (R-9)
- [ ] Extraction-quality gate still passes (R-11)
- [ ] Deterministic output / seeded sampling (R-12, R-13)
- [ ] Model artifact has full meta.json (R-14, R-15)
- [ ] mock vs real handled correctly (R-16..R-18)
- [ ] Module boundaries respected (R-19..R-22)
- [ ] Tests added, offline, in this PR (R-34..R-37)
- [ ] No secrets; keys hashed (R-38, R-39)
```
