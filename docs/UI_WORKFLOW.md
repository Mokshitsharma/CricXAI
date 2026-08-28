# CricXAI — UI Workflow

Status: Draft v1 · Last updated: 2026-08-28
Companion: [DESIGN.md](DESIGN.md), [APP_FLOW.md](APP_FLOW.md).

Screen-by-screen: what the user does, what the UI shows, and every state.

---

## 1. Site map

```
/                      Landing (value prop, demo CTA)
/console               Strategy console (core) — auth optional for demo, gated by quota
/batsmen               Batsman search / index
/batsmen/[id]          Batsman vulnerability profile (SSR, indexable)
/matches               Match browser
/matches/[id]          Match timeline → jump into console
/scenarios             Saved scenarios (auth)
/account               Plan, usage, API keys, billing (auth)
/docs                  API documentation (Phase 5)
/sign-in /sign-up      Auth (Phase 5; demo works without)
```

## 2. Primary workflow — get a recommendation

```mermaid
flowchart TD
  A[Open /console] --> B{First visit?}
  B -- yes --> C[Prefilled example situation\nIND v AUS, over 43, 271/6, chasing 322]
  B -- no --> D[Restore last situation from localStorage]
  C --> E[Results render for the example]
  D --> E
  E --> F[User edits any field in SituationBuilder]
  F --> G[Debounced 250ms -> POST /v1/recommendation]
  G --> H{Response}
  H -- ok --> I[Primary card + alternatives + heatmap + field update]
  H -- low sample --> J[Muted probability range + warn note + reasons still shown]
  H -- 422 no history --> K[Empty result panel: 'Not enough data on this batsman']
  H -- 429 quota --> L[Quota modal: sign in / upgrade]
  H -- network/5xx --> M[Inline retry in results panel; builder stays usable]
  I --> N[User clicks an alternative]
  N --> O[That delivery becomes primary; field + heatmap ring move; no refetch]
  I --> P[User clicks 'Save scenario' (auth)]
  P --> Q[POST /v1/scenarios -> toast 'Saved']
```

### SituationBuilder fields

| Field | Control | Rules |
| --- | --- | --- |
| Match | combobox (search teams/date) | optional; sets default batsman list + venue context |
| Batsman | async search combobox | required; shows team + sample size in the option row |
| Bowler type | segmented control (5 options) | required; default `pace_right_arm` |
| Over | stepper 0–49 | drives `phase` (read-only chip) |
| Ball in over | stepper 1–6 | |
| Score | number | ≥ 0 |
| Wickets | stepper 0–9 | |
| Innings | toggle 1 / 2 | if 2, `Target` appears |
| Target | number | required when innings 2; must be > score |

Validation is inline and non-blocking where possible; the request only fires
when the payload is valid. Invalid field → red hairline + helper text, last
good result stays on screen dimmed.

## 3. States (every async surface)

| Surface | Loading | Empty | Error | Low-sample | Success |
| --- | --- | --- | --- | --- | --- |
| Recommendation card | skeleton of the card shape | "Pick a batsman to begin" | inline retry + request id | probability shown as a range, `--warn` note "based on N dismissals" | full card + 3 reasons + confidence badge |
| Heatmap | shimmer grid | hidden until batsman chosen | "Couldn't load heatmap — retry" | cells with < k samples hatched + tooltip "low sample" | coloured grid, recommended cell ringed |
| Field diagram | static neutral field | neutral field, no zones | neutral field + toast | zones faint | preset dots + scoring zones |
| Batsman search | spinner in field | "No batsman matches 'xyz'" | "Search failed — retry" | n/a | option list with team + sample |
| Profile page | SSR skeleton | 404 if unknown id | error boundary page | banner "Limited data: N dismissals across M matches" | full panels |
| Usage meter | bar skeleton | n/a | "—" with retry | n/a | used / quota + reset date |

## 4. Match timeline → console handoff

1. `/matches/[id]` shows innings tabs and a scrollable ball list (over.ball,
   batsman, bowler, outcome, mini commentary if present).
2. Each row has a "▷ Analyse" affordance.
3. Click → navigate to `/console?match=<id>&innings=<n>&over=<o>&ball=<b>&score=<s>&wickets=<w>&batsman=<id>&bowler_type=<t>`.
4. Console hydrates the builder from the query string and fires the request.
5. A subtle banner: "Analysing the situation before the 43.2 delivery —
   [clear]".

## 5. Auth & quota touchpoints

- Demo mode: `/console` works unauthenticated up to the anonymous daily cap
  (cookie-based). On cap → non-dismissable-but-skippable modal: "You've used
  today's free analyses. Sign in for more."
- Signed-in free plan: higher cap; the UsageMeter appears in the header.
- Hitting the plan cap → `/account` upsell with the exact number remaining
  and reset time.
- API keys are created in `/account`; the secret is shown **once** in a copy
  box with a "you won't see this again" warning, then only the prefix.

## 6. Responsiveness

- ≥ 1024px: two-column console (builder | results), heatmap + field
  side-by-side below.
- 768–1023px: builder collapses to a top sheet ("Edit situation" button),
  results full width, heatmap above field.
- < 768px: single column; builder is a bottom sheet; primary card, then
  alternatives, then heatmap (horizontal scroll), then field.

## 7. Empty-project / no-model fallback

If the API reports no `active` model (`503`), the console shows a single
centered message: "Models are being trained — check back shortly." The
builder is disabled. This is the state right after a fresh checkout before
`scripts/train.py` has run.

## 8. Micro-copy principles

- Name the delivery like a cricketer: "Yorker, off stump", not
  "length=yorker, line=off_stump".
- Reasons are full sentences with the comparison baked in.
- Never show a raw enum or an encoded integer in the UI.
- Uncertainty is stated, not hedged away: "Low confidence — 9 dismissals."
