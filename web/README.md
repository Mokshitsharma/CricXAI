# CricXAI web console

## Design

`web/design/` holds the design-canvas source — three artboards
(`Main.dc.html` = Strategy Console, `Profile.dc.html` = batsman
vulnerability profile, `Timeline.dc.html` = match timeline) plus
`canvas.json`. Published, interactive canvas:

<https://claude.ai/code/artifact/c998fc62-0bfe-4bfb-82ec-743fd1a8da71>

Design language and tokens are specified in
[`../docs/DESIGN.md`](../docs/DESIGN.md); screen-by-screen flows and states
in [`../docs/UI_WORKFLOW.md`](../docs/UI_WORKFLOW.md). Clean, minimalist,
monochrome + one pitch-green accent (`#1F6F5C` / dark `#3FA98C`),
Inter / IBM Plex Sans, hairline borders, tabular numerals, light + dark.

The seeded `cricxai-strategy-console.html` (~2.5 MB, gitignored) is a build
artifact. Regenerate it from the sources:

```bash
cd web/design
node "<design-skill>/seed-canvas.mjs" \
  --template "<design-skill>/payload.template.html" \
  --out cricxai-strategy-console.html --title "CricXAI Strategy Console" \
  --artboard Main.dc.html --artboard Profile.dc.html --artboard Timeline.dc.html \
  --canvas canvas.json
```

To edit the canvas: change the `.dc.html` files, re-seed, and republish to
the same artifact URL.

## App (to build — Sprint 5 in docs/IMPLEMENTATION_PLAN.md)

Planned stack: Next.js 14 (App Router, TS strict), Tailwind + shadcn/ui with
the DESIGN.md tokens, TanStack Query, an `/v1` client generated from the
API's OpenAPI schema (`GET /v1/openapi.json`).

Routes: `/`, `/console`, `/batsmen`, `/batsmen/[id]`, `/matches`,
`/matches/[id]`, `/account`.

Components to port from the artboards: `SituationBuilder`,
`RecommendationCard`, `AlternativesList`, `LengthLineHeatmap` (SVG),
`FieldDiagram` (SVG), `ConfidenceBadge`, and the loading / empty / error /
low-sample / no-model states from UI_WORKFLOW.md §3.

The console calls the same public API the docs describe — run it locally with:

```bash
cd ..
python -m scripts.mock_data --num-matches 100 --seed 42
python -m scripts.build_features
python -m scripts.train
python -m uvicorn app.api.main:app --reload --port 8000
```

Then point `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
