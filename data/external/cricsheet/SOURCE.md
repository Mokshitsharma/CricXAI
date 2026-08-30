# Cricsheet ODI data

- **File:** `odis_json.zip` (JSON v1.2.0, one file per match + `README.txt`)
- **Source:** <https://cricsheet.org/downloads/odis_json.zip>
- **Downloaded:** 2026-08-30
- **Contents:** 3,176 One-day International matches, 2002-06-27 -> 2026-08-17
  (2,569 male, 607 female). 917k+ deliveries in matches between two of
  CricXAI's ten target nations.
- **Format docs:** <https://cricsheet.org/format/json/>

## Licence

Cricsheet publishes match data under the **Open Data Commons Attribution
License (ODC-BY 1.0)** — free to use and to build derivative works from,
**attribution required**. Confirm the current terms on cricsheet.org before
any commercial / monetised release, and carry a visible "Data: Cricsheet
(ODC-BY)" credit in the product.

## Known gaps (see `docs/PHASES.md`)

- **No ball length / line / shot type / speed / pitch-map.** Cricsheet is
  scorecard + outcome granularity only. The length x line recommendation
  layer cannot be trained from this source (`ball_length` / `ball_line` /
  `shot_type` are ingested as `"unknown"`).
- **No Afghanistan men's matches** — withheld by Cricsheet policy. 159 ODIs
  withheld in total.
- **No bowler type** (pace/spin/hand). Supplied separately via
  `data/reference/bowler_types.csv` (TODO).

## Regenerating the processed tables

```bash
python -m scripts.cricsheet_ingest            # -> data/processed/{deliveries,matches}.csv
python -m scripts.build_features
python -m scripts.train
```
