# CricXAI — Design

Status: Draft v1 · Last updated: 2026-08-28
Companion: [UI_WORKFLOW.md](UI_WORKFLOW.md) (flows/states),
[APP_FLOW.md](APP_FLOW.md) (runtime).

Design principle: **clean, simple, minimalist.** The product's value is a
single confident answer plus its reasons. The interface should feel like a
well-set field — nothing in it that isn't doing a job.

---

## 1. Design tenets

1. **One answer, foregrounded.** The top recommendation is the largest thing
   on the screen. Alternatives and the full heatmap are secondary.
2. **Show the delta, not just the number.** "Averages 12 at the death vs 41
   in the middle" beats "death average: 12".
3. **Explain by default.** Reasons are always visible on the primary card,
   not behind a click.
4. **Calm surface, honest uncertainty.** Low sample and low confidence look
   visibly different — muted, flagged — never dressed up as certainty.
5. **Monochrome + one accent.** Colour carries meaning (danger on the
   heatmap, confidence), never decoration.
6. **Fast and legible on a tablet at the boundary rope.** Large hit targets,
   high contrast, works in sunlight and in a dark press box.

## 2. Visual language

### Colour (tokens — light / dark)

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--bg` | `#FBFBFA` | `#0E0F11` | page |
| `--surface` | `#FFFFFF` | `#17191C` | cards |
| `--border` | `#E8E6E1` | `#2A2D31` | hairlines |
| `--text` | `#1A1A1A` | `#ECECEC` | primary text |
| `--text-muted` | `#6B6B6B` | `#9A9A9A` | secondary |
| `--accent` | `#1F6F5C` (pitch green) | `#3FA98C` | primary action, links |
| `--danger-scale` | 5-step sequential, pale sand → deep rust | same hues, adjusted L | heatmap "how dangerous to bowl here" |
| `--good` | `#2E7D32` | `#66BB6A` | positive delta |
| `--warn` | `#B26A00` | `#E0A030` | low sample / caution |

Heatmap uses a **single-hue sequential** ramp (safe → dangerous). Never
red/green diverging — colour-blind hostile and implies a midpoint that
doesn't exist. Every heatmap cell also shows its numeric value.

### Typography

- One family: a clean grotesque (Inter / IBM Plex Sans) with a system
  fallback stack. Tabular numerals on for all stats.
- Scale: 12 / 14 / 16 / 20 / 28 / 40. Body 16, card labels 12 (uppercase,
  tracked), the headline probability at 40.
- Weight: 400 body, 500 labels, 600 the one headline number. No 700.

### Space & shape

- 8px spacing grid. Card padding 24. Section gap 32.
- Radius 10 on cards, 8 on controls, 0 on the heatmap grid (cells butt
  together).
- Hairline borders (`1px --border`), no drop shadows except a single soft
  shadow on the active recommendation card to lift it.
- Max content width 1120px; the console is a two-column layout
  (situation builder left ~360px, results right).

### Motion

- 120–160ms ease-out on state changes. The heatmap cells cross-fade on
  batsman change. No bouncing, no parallax, nothing decorative.
- Respect `prefers-reduced-motion`.

## 3. Core components

| Component | Description |
| --- | --- |
| **SituationBuilder** | Left column. Match picker, batsman search, bowler-type segmented control, phase auto-derived from over, sliders/steppers for over, ball, score, wickets, target. Live — every change re-requests. |
| **RecommendationCard (primary)** | Big length+line statement ("Yorker, off stump"), the dismissal probability at 40px with a confidence badge, expected runs, the field preset name, and 3 reasons as plain sentences. One soft shadow. |
| **AlternativesList** | Ranks 2–3 as compact rows: length/line, prob, E[runs]. Click promotes to primary (and updates the field diagram + heatmap highlight). |
| **LengthLineHeatmap** | 5 lengths × 7 lines grid, sequential danger colour + value in each cell, recommended cell ringed. Hover/focus shows that cell's prob, E[runs], and sample size. Keyboard-navigable. |
| **FieldDiagram** | Top-down half-oval, 9 fielder dots for the current preset, batsman scoring-zone shading behind them. SVG, theme-aware, printable. |
| **VulnerabilityPanel** (profile page) | Small multiples: dismissal-type %, length %, line %, phase average bars, pressure vs normal. Deltas vs dataset average called out. |
| **ConfidenceBadge** | `high` / `medium` / `low` pill; `low` also shows a one-line "based on N dismissals" note in `--warn`. |
| **EmptyState / LowSampleState / ErrorState** | Explicit. Low-sample greys the probability and swaps it for a range. |
| **UsageMeter** (account) | Simple bar: calls used / quota, period reset date. |

## 4. Key screens (layout intent)

### Strategy Console (`/console`)
```
┌───────────────────────────── CricXAI ─────────────── acct ─┐
│ ┌── Situation ─────────┐  ┌── Recommendation ─────────────┐ │
│ │ Match:  IND v AUS ▾  │  │  YORKER · OFF STUMP           │ │
│ │ Batsman: [ search  ] │  │                               │ │
│ │ Bowler: (pace)(off▸) │  │     8.1%   dismissal   [med]   │ │
│ │ Over  43   Ball 2    │  │     E[runs] 1.1               │ │
│ │ Score 271  Wkts 6    │  │  Field: death yorker ring     │ │
│ │ Target 322           │  │  • Bowled on 34% of his outs  │ │
│ │ Phase: death (auto)  │  │  • Death avg 12 vs 41 middle  │ │
│ └─────────────────────┘  │  • Dot% climbs under pressure  │ │
│                          └───────────────────────────────┘ │
│ ┌── Length × Line ───────┐  ┌── Field ────────────────────┐ │
│ │ [ 5 x 7 heatmap ]      │  │ [ top-down field diagram ]  │ │
│ └───────────────────────┘  └─────────────────────────────┘ │
│ Alternatives:  2) Full · wide out off  6.0% · 1.4         │
│                3) Short · off stump    5.2% · 1.7         │
└───────────────────────────────────────────────────────────┘
```

### Batsman Profile (`/batsmen/[id]`) — server-rendered
Header (name, team, hand, sample size) · VulnerabilityPanel small multiples ·
"Most dangerous deliveries" mini-heatmap · link "Open in console".

### Match Browser (`/matches` , `/matches/[id]`)
List of matches (teams, date, result). Match page: innings tabs, ball-by-ball
timeline; click any ball → opens the console pre-filled with that situation
("what should they have bowled here?").

### Account (`/account`)
Plan + UsageMeter, API keys (create → shown once → list with prefix),
billing portal link, saved scenarios.

## 5. Data-viz rules (see also the `dataviz` skill)

- Sequential single-hue for the danger heatmap; categorical (max 6, muted)
  for dismissal-type breakdowns.
- Every chart: real axis labels, value labels where space allows, a caption
  stating the sample ("42 dismissals, 8 matches").
- No dual axes. No pie charts except the single dismissal-type donut on the
  profile, with a legend and values.
- Wide charts scroll inside their own container; the page never scrolls
  sideways.

## 6. Accessibility

- WCAG 2.1 AA contrast on text and on heatmap cell text over its fill.
- Full keyboard path: builder fields → heatmap cells (arrow keys) →
  alternatives → field presets.
- Heatmap and field dots have `aria-label`s with the underlying numbers.
- Focus rings visible (2px `--accent`), never removed.
- Colour is never the only signal: heatmap cells show numbers, confidence
  shows text.

## 7. Design deliverable

The visual design is drafted as a design canvas of artboards: Console
(light + dark), Batsman Profile, Match timeline, Account. Frontend
implements against those artboards with Tailwind + shadcn/ui and the tokens
in §2. Sources live in `web/design/`.
