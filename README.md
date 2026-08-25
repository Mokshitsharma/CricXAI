# CricXAI

CricXAI is a prescriptive cricket strategy platform. Instead of just
reporting what a batsman has done historically, it recommends what a
bowling team should do *right now* against a specific batsman in a specific
match situation — delivery length and line, field placement, dismissal
probability and type, with SHAP-based reasoning.

## Status

This is an early-stage build. Data collection and feature engineering
(Pillar 1) are implemented and tested. The FastAPI service, ML models, SHAP
explanations, and monetization layer are not yet built.

## Project structure

```text
scripts/
  match_ids.py       # resolve ODI match IDs to scrape (API + manual fallback)
  scraper.py          # scrape ESPNcricinfo commentary, one JSON file per match
  nlp_parser.py        # commentary text -> structured ball-by-ball data
  build_features.py    # ball-by-ball data -> ML-ready feature table
app/
  utils/
    logger.py           # shared logging config
    file_io.py           # JSON/YAML/dir helpers
    cricket_constants.py # shared phase/length/line/dismissal vocabulary
data/
  raw/       # one JSON file per scraped match (committed to git intentionally)
  processed/ # deliveries.csv, matches.csv, delivery_features.csv (gitignored)
  models/    # trained model artifacts, once they exist (gitignored)
  logs/      # scrape run logs (committed to git intentionally)
tests/
  scripts/   # pytest coverage for the four scripts above, offline/synthetic
```

## Setup

```bash
pip install -r requirements.txt
```

## Data pipeline

### 1. Resolve match IDs

```bash
python -m scripts.match_ids --init-manual-file
```

Creates `data/match_ids_manual.json` for hand-curating match IDs per
tournament. ESPNcricinfo does not publish a stable "list every ODI match"
endpoint, so `scripts/match_ids.py` tries a best-effort series-schedule API
call first (configure a series ID in `scripts.match_ids.TOURNAMENTS`) and
falls back to whatever you've entered in the manual file.

```bash
python -m scripts.match_ids --tournament world_cup_2023
```

### 2. Scrape commentary

```bash
python -m scripts.scraper --tournament world_cup_2023 --batch-size 15
```

Scrapes up to `--batch-size` not-yet-saved matches from
`hs-consumer-api.espncricinfo.com`'s commentary endpoint, saving one combined
JSON file per match to `data/raw/{match_id}.json`. Idempotent — a match
already on disk is skipped without a network call. Polite by default: 2.5s
between page requests, 5s between matches, a 15s pause every 5 matches.

**Note:** this endpoint is unofficial and can 403 requests from some
networks/IP ranges (observed during development from a sandboxed CI-like
environment — even the plain espncricinfo.com homepage was blocked there).
If scraping fails everywhere, verify from a normal residential/browser
network first before assuming the code is broken, and check whether this
also affects the GitHub Actions runner IPs before relying on the scheduled
cron workflow.

### 3. Parse commentary into structured data

```bash
python -m scripts.nlp_parser --input-dir data/raw --output-dir data/processed
```

Extracts ball length, line, shot type (via phrase-matching dictionaries),
outcome, and dismissal type from each delivery's commentary text. Writes
`deliveries.csv` (one row per ball) and `matches.csv` (one row per match).
Logs what percentage of rows each field was successfully extracted for —
watch this if you add new tournaments, since ESPN's phrasing can vary.

### 4. Build ML features

```bash
python -m scripts.build_features --input data/processed/deliveries.csv --output data/processed/delivery_features.csv
```

Engineers match-context (phase, score, wickets, pressure index), batsman/
bowler rolling stats (this innings/spell only), and batsman historical
vulnerability features (dismissal type / length / line breakdown, phase
averages, pressure vs. normal splits) — all computed using only information
available before each ball, and historical features are computed across
every match *except* the one the row belongs to, to avoid leakage once this
becomes training data.

## Testing

```bash
python -m pytest tests/ -v
```

All tests run offline against small synthetic fixtures — no network access
or scraped data required.
