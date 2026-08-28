# CricXAI — Product Requirements Document (PRD)

Status: Draft v1 · Owner: Product · Last updated: 2026-08-28

---

## 1. Overview

CricXAI is a **prescriptive** cricket strategy platform. Where existing
analytics tools describe what a batsman has done (averages, wagon wheels,
pitch maps), CricXAI recommends what a bowling team should do **right now**
against a specific batsman in a specific match situation:

- the delivery to bowl — **length** and **line** (and, later, variation)
- the **field** to set
- the **probability of a dismissal** on the next ball and the most likely
  **dismissal type**
- a plain-language **explanation** of the recommendation, backed by SHAP
  feature attributions

## 2. Problem statement

Bowling teams make in-over tactical decisions from memory, gut feel, and a
coach's shouted advice. The data to do better exists (ball-by-ball history,
dismissal patterns, situational context) but is not packaged as an
actionable, situation-aware recommendation. Analysts can produce a dossier
before a match; nobody produces a per-ball recommendation during one that a
captain can act on in ten seconds.

## 3. Goals and non-goals

### Goals

1. Given `{match situation, batsman, bowler type}`, return a ranked delivery
   recommendation with calibrated dismissal probability in < 500 ms (p95).
2. Every recommendation is explainable: top contributing factors shown in
   language a cricketer understands.
3. Recommendations are grounded in leakage-free historical data — no feature
   may use information unavailable before the ball is bowled.
4. Ship a usable web console and a documented REST API.
5. Monetize via subscription tiers plus metered API usage.

### Non-goals (v1)

- Batting-side recommendations (what shot to play).
- Real-time video / ball-tracking ingestion (Hawk-Eye). We use commentary
  text only.
- Formats other than **ODI** in v1 (T20 and Test are Phase 5+).
- Live automated data feeds during a match — v1 uses the user entering the
  situation manually or picking a historical situation.
- Team/club account management and role hierarchies (Phase 6).

## 4. Target users and personas

| Persona | Description | Primary need |
| --- | --- | --- |
| ** Analyst Aarti** | Team performance analyst preparing bowling plans | Batter vulnerability profiles, exportable plans, API access |
| **Coach Rahul** | Assistant coach running the bowling unit | Fast, readable per-situation recommendations on a tablet |
| **Broadcaster Sam** | TV/streaming analyst wanting a talking point | "What should they bowl here?" graphic with reasoning |
| **Fantasy / bettor Priya** | Advanced fantasy player | Dismissal probability by situation, API for models |
| **Developer Dan** | Builds a cricket product | Clean REST API, predictable pricing, SDK |

## 5. User stories

### Recommendation (core)

- As an analyst, I select a match, batsman, bowler type, over, score, and
  wickets, and I get the top 3 recommended deliveries with a dismissal
  probability and expected runs for each.
- As a coach, I see a length × line heatmap for the selected batsman in this
  phase, so I can see the whole picture, not just the single best cell.
- As any user, I click a recommendation and see the 5 biggest reasons for it
  ("caught in the deep is 3× more likely for this batsman under pressure",
  "he averages 11 vs the short ball outside off in the death").
- As any user, I see a suggested field (preset name + fielder positions) that
  matches the recommended delivery and the batsman's scoring zones.

### Exploration

- As an analyst, I open a batsman's profile and see dismissal-type,
  length, and line breakdowns, phase averages, and pressure vs. normal
  splits.
- As a user, I browse the matches in the dataset and jump into any point in
  any innings as a "what should they have bowled here?" scenario.
- As a user, I save a scenario and revisit it later.

### API / account

- As a developer, I create an API key and call `POST /v1/recommendation`
  with a JSON situation and get the same result the console shows.
- As a user, I see my monthly usage and upgrade my plan when I hit a limit.
- As a user, I sign in with email or Google.

## 6. Features by pillar

| Pillar | Feature | Status |
| --- | --- | --- |
| **1. Data & features** | ESPNcricinfo commentary scraper (idempotent, polite) | Done |
| | Commentary → structured deliveries (NLP phrase parsing) | Done |
| | Leakage-free feature engineering (situation + history) | Done |
| | Match-ID resolution (API + manual fallback) | Done |
| | Scheduled scrape (GitHub Actions cron) | Planned |
| | Move CSV artifacts into Postgres + object storage | Planned |
| **2. Models** | Dismissal probability (binary, calibrated) | Planned |
| | Dismissal type (multiclass, conditional on wicket) | Planned |
| | Expected runs per candidate delivery (regressor) | Planned |
| | Recommendation engine (score candidate deliveries, rank) | Planned |
| | Field placement mapping (heuristic → model) | Planned |
| | Model registry + versioning + offline eval harness | Planned |
| **3. Explanations** | SHAP attributions per prediction | Planned |
| | Cricket-language reason templates | Planned |
| **4. Serving** | FastAPI service, REST v1 | Planned |
| | Web console (situation builder, heatmap, field, reasons) | Planned |
| | Batsman profile pages, match browser, saved scenarios | Planned |
| **5. Monetization** | Auth, API keys, plans, Stripe subscriptions, metered usage | Planned |
| | Usage dashboard and quota enforcement | Planned |

## 7. Functional requirements

- **FR-1** The system SHALL accept a match situation as: innings (1/2),
  over (0–49), ball-in-over (1–6), current score, wickets down, target (if
  chasing), batsman identity, bowler type.
- **FR-2** The system SHALL return, for a situation, a ranked list of up to 5
  candidate deliveries; each item has `{length, line, dismissal_probability,
  expected_runs, field_preset, reasons[]}`.
- **FR-3** `dismissal_probability` SHALL be a calibrated probability in
  `[0, 1]` (Brier score and reliability curve reported at training time).
- **FR-4** `reasons[]` SHALL contain 3–6 human-readable strings derived from
  SHAP values and reason templates, ordered by contribution magnitude.
- **FR-5** The system SHALL expose a batsman vulnerability profile:
  dismissal-type %, length %, line %, phase average, pressure/normal average.
- **FR-6** The system SHALL let a signed-in user save and reload a scenario.
- **FR-7** The API SHALL be authenticated by API key; each call SHALL be
  metered against the caller's plan quota.
- **FR-8** The data pipeline SHALL be reproducible from raw JSON with a
  single documented command sequence.
- **FR-9** No engineered feature may use post-ball information for a given
  row; historical aggregates for a row SHALL exclude that row's own match.

## 8. Non-functional requirements

| Attribute | Target |
| --- | --- |
| Recommendation latency | p50 < 150 ms, p95 < 500 ms (warm model, cached features) |
| API availability | 99.5% monthly (v1), 99.9% (v2) |
| Model refresh | Retrain monthly or when new tournament added; zero-downtime swap |
| Data freshness | New matches scraped within 48h of completion |
| Explainability | 100% of recommendations carry reasons |
| Reproducibility | Feature build is deterministic given the same raw inputs |
| Accessibility | WCAG 2.1 AA for the console |
| Privacy | Only account data (email, plan, usage) is personal; no PII in cricket data |

## 9. Success metrics

**Product**

- Time-to-first-recommendation for a new user < 3 minutes.
- ≥ 60% of weekly active users run ≥ 5 recommendations per session.
- ≥ 30% of API-tier signups make a second-week call.

**Model quality (offline, held-out matches)**

- Dismissal probability: Brier score beating the base-rate baseline by ≥ 15%;
  reliability curve within ±0.03 of diagonal in the 0–0.2 band.
- Dismissal type: macro-F1 ≥ 0.45 (6 classes, conditional on wicket).
- Recommendation: on held-out balls, the model's top-ranked length/line
  matches or beats the actually-bowled delivery on realized wicket rate in
  aggregate (backtest uplift metric, see TRD §7).

**Business**

- Free → paid conversion ≥ 4% within 60 days.
- Monthly churn < 6% on paid plans.

## 10. Monetization

| Plan | Price (indicative) | Console | API calls / mo | History | Support |
| --- | --- | --- | --- | --- | --- |
| Free | $0 | Yes, 20 recs/day | 100 | Last 1 tournament | Community |
| Pro | $19/mo | Unlimited | 5,000 | All | Email |
| Analyst | $99/mo | Unlimited + export | 50,000 | All + bulk export | Priority |
| API / Business | usage-based | — | metered ($ per 1k) | All | SLA |

Billing via Stripe (subscriptions + metered usage records). Quota enforced
at the API gateway and the console.

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| ESPNcricinfo endpoint blocks / changes shape | No new data | Defensive parsing already in place; manual match-id fallback; monitor extraction-quality logs; be ready to swap source |
| Scraping legality / ToS | Existential | Use only for internal modeling; do not redistribute raw commentary; consult licensed data feed before scale; keep raw store private |
| Commentary phrasing varies by writer → poor length/line extraction | Weak features | Extraction-quality logging per field; expand phrase dictionaries; consider a small trained text classifier in Phase 4 |
| Small dataset → overfit models | Bad recommendations | Held-out-by-match CV; conservative models (GBDT with regularization); report calibration; ship "low confidence" flag |
| Recommendation is "obvious" (bowl yorkers at the death) | Low perceived value | Lead with the vulnerability *deltas* and the field, not just the cell; surface non-obvious pressure splits |
| Leakage creeping back in as features grow | Silent model inflation | Leakage rules in RULES.md; a leakage unit-test suite; feature review checklist |

## 12. Out of scope for v1

Batting recommendations, video ingestion, non-ODI formats, live data feeds,
mobile native apps, multi-user team accounts, in-app collaboration.

## 13. Open questions

- Do we license a commercial ball-by-ball feed before public launch, or ship
  on scraped data with a disclaimer?
- Is field placement a heuristic layer for v1, or do we need a shot-direction
  model first?
- What is the minimum match count per tournament before a batsman's profile
  is shown without a "low sample" warning?

See [PHASES.md](PHASES.md) for the delivery plan and
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for tasks.
