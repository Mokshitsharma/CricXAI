"""Engineer ML-ready features from parsed ball-by-ball deliveries.

Every feature here is computed from information available *before* the
current ball is bowled — either "so far this innings/spell" rolling stats,
or historical stats computed across every match *except* the one the current
row belongs to (a naive "all matches including this one" average would leak
the outcome of the very ball being predicted into its own features once this
becomes training data).

Two simplifications, documented rather than hidden, given what
``nlp_parser.py`` currently extracts:
- ``total_runs`` is treated as the batsman's runs off the bat for
  rolling/strike-rate purposes; byes/leg-byes aren't separately tracked yet.
- "Bowler spell" rolling stats are cumulative per (match, innings, bowler)
  rather than per distinct spell, since spell boundaries aren't parsed yet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from app.utils.cricket_constants import (
    BALL_LENGTH_ENCODING,
    BALL_LINE_ENCODING,
    DISMISSAL_TYPE_ENCODING,
    DISMISSAL_TYPES,
    PHASE_ENCODING,
    UNKNOWN_ENCODING,
    phase_from_over,
)
from app.utils.file_io import write_frame
from app.utils.logger import get_logger

DEFAULT_INPUT_PATH = Path("data/processed/deliveries.csv")
DEFAULT_OUTPUT_PATH = Path("data/processed/delivery_features.csv")
BALLS_PER_OVER = 6
TOTAL_OVERS = 50
PRESSURE_CAP = 10.0
PRESSURE_WICKET_WEIGHT = 2.0
UNDER_PRESSURE_THRESHOLD = 5.0
# Rolling strike rate off a 1-2 ball denominator can spike into the hundreds
# of thousands; clip it to a cricket-plausible ceiling so it doesn't dominate
# tree splits. Real sustained ODI strike rates top out well below this.
STRIKE_RATE_CAP = 400.0


def _sort_deliveries(df: pd.DataFrame) -> pd.DataFrame:
    """Sort into strict chronological order within each match/innings."""
    return df.sort_values(
        ["match_id", "innings", "over", "ball_in_over"],
        kind="stable",
    ).reset_index(drop=True)


def add_phase(df: pd.DataFrame) -> pd.DataFrame:
    df["phase"] = df["over"].apply(phase_from_over)
    df["phase_encoded"] = df["phase"].map(PHASE_ENCODING).fillna(UNKNOWN_ENCODING).astype(int)
    return df


def add_batsman_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Runs/balls/SR/dot% for this batsman, this innings, strictly before this ball."""
    # NOTE: `.groupby(...).cumsum().shift(1)` is a trap — cumsum() respects
    # group boundaries but a plain `.shift(1)` chained after it does not, so
    # it can pull in the last value of the *previous* group. Always shift
    # inside a `.transform(lambda s: ...)` so both cumsum and shift are
    # scoped to the same group.
    group_cols = ["match_id", "innings", "batsman"]
    is_faced_ball = (df["outcome"] != "wide").astype(int)
    is_dot = (df["outcome"] == "dot").astype(int)

    df["batsman_runs_so_far"] = (
        df["total_runs"].fillna(0).groupby([df[c] for c in group_cols]).transform(
            lambda s: s.cumsum().shift(1).fillna(0)
        )
    )
    df["batsman_balls_faced"] = is_faced_ball.groupby([df[c] for c in group_cols]).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    df["batsman_strike_rate"] = np.clip(
        np.where(
            df["batsman_balls_faced"] > 0,
            100.0 * df["batsman_runs_so_far"] / df["batsman_balls_faced"],
            0.0,
        ),
        0.0,
        STRIKE_RATE_CAP,
    )
    dots_so_far = is_dot.groupby([df[c] for c in group_cols]).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    df["batsman_dot_pct"] = np.where(
        df["batsman_balls_faced"] > 0,
        100.0 * dots_so_far / df["batsman_balls_faced"],
        0.0,
    )
    return df


def add_bowler_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Balls/wickets/economy for this bowler, this innings, strictly before this ball."""
    group_cols = ["match_id", "innings", "bowler"]
    is_legal_ball = (~df["outcome"].isin(["wide", "no_ball"])).astype(int)

    df["bowler_balls_bowled"] = is_legal_ball.groupby([df[c] for c in group_cols]).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    df["bowler_wickets_so_far"] = df["is_wicket"].astype(int).groupby([df[c] for c in group_cols]).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    runs_conceded_so_far = df["total_runs"].fillna(0).groupby([df[c] for c in group_cols]).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    overs_bowled_so_far = df["bowler_balls_bowled"] / BALLS_PER_OVER
    df["bowler_economy"] = np.where(
        overs_bowled_so_far > 0,
        runs_conceded_so_far / overs_bowled_so_far,
        0.0,
    )
    return df


def add_match_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """Innings score/wickets so far, and pressure_index for chasing teams."""
    group_cols = ["match_id", "innings"]
    key = [df[c] for c in group_cols]
    df["innings_score"] = df["total_runs"].fillna(0).groupby(key).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    df["innings_wickets"] = df["is_wicket"].astype(int).groupby(key).transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )

    innings_totals = (
        df.groupby(["match_id", "innings"])["total_runs"].sum().rename("innings_total").reset_index()
    )
    first_innings_totals = innings_totals[innings_totals["innings"] == 1][["match_id", "innings_total"]]
    first_innings_totals = first_innings_totals.rename(columns={"innings_total": "target"})
    first_innings_totals["target"] = first_innings_totals["target"] + 1
    df = df.merge(first_innings_totals, on="match_id", how="left")

    # ball_in_over is 1-indexed (this ball is the Nth of the over, about to be
    # bowled), so balls already completed this over is (ball_in_over - 1).
    balls_completed_this_over = (df["ball_in_over"].fillna(1) - 1).clip(lower=0)
    overs_completed = df["over"] + (balls_completed_this_over / BALLS_PER_OVER)
    overs_remaining = (TOTAL_OVERS - overs_completed).clip(lower=0.01)
    current_run_rate = np.where(overs_completed > 0, df["innings_score"] / overs_completed.replace(0, np.nan), 0.0)
    current_run_rate = np.nan_to_num(current_run_rate, nan=0.0)
    required_run_rate = np.where(
        df["innings"] == 2,
        (df["target"] - df["innings_score"]) / overs_remaining,
        0.0,
    )

    is_chasing = df["innings"] == 2
    raw_pressure = (required_run_rate - current_run_rate) + (df["innings_wickets"] / 10.0 * PRESSURE_WICKET_WEIGHT)
    # Clip to [0, CAP] for chasing rows — a cruising chase yields a large
    # negative raw value, and app/api/service.compute_pressure_index floors
    # at 0 at serve time, so training must match (docs/RULES.md R-5).
    df["pressure_index"] = np.where(
        is_chasing, np.clip(raw_pressure, 0.0, PRESSURE_CAP), 0.0
    )
    df = df.drop(columns=["target"])
    return df


def _leakage_free_rate(
    df: pd.DataFrame,
    subset: pd.DataFrame,
    category_col: str,
    categories: tuple[str, ...],
) -> pd.DataFrame:
    """Per-row (batsman, category) rate computed over every OTHER match.

    ``subset`` is the rows to aggregate over (e.g. only dismissal rows).
    Returns one column per category named ``{category_col}_{category}``,
    each a percentage of that batsman's ``subset`` rows in other matches
    that fall into that category.
    """
    total_counts = subset.pivot_table(
        index="batsman", columns=category_col, aggfunc="size", fill_value=0
    )
    per_match_counts = subset.pivot_table(
        index=["batsman", "match_id"], columns=category_col, aggfunc="size", fill_value=0
    )

    for category in categories:
        if category not in total_counts.columns:
            total_counts[category] = 0
        if category not in per_match_counts.columns:
            per_match_counts[category] = 0
    total_counts = total_counts[list(categories)]
    per_match_counts = per_match_counts[list(categories)]

    total_for_row = df.merge(
        total_counts.add_suffix("_total"), left_on="batsman", right_index=True, how="left"
    )
    this_match_for_row = df.merge(
        per_match_counts.add_suffix("_this_match"),
        left_on=["batsman", "match_id"],
        right_index=True,
        how="left",
    )

    result = pd.DataFrame(index=df.index)
    other_total = pd.Series(0.0, index=df.index)
    other_counts: dict[str, pd.Series] = {}
    for category in categories:
        total_col = total_for_row[f"{category}_total"].fillna(0).to_numpy()
        this_match_col = this_match_for_row[f"{category}_this_match"].fillna(0).to_numpy()
        other = np.maximum(total_col - this_match_col, 0.0)
        other_counts[category] = pd.Series(other, index=df.index)
        other_total = other_total + other

    for category in categories:
        column_name = f"hist_{category_col}_{category}_pct"
        result[column_name] = np.where(
            other_total > 0, 100.0 * other_counts[category] / other_total, 0.0
        )
    return result


def add_historical_batsman_features(df: pd.DataFrame) -> pd.DataFrame:
    """Batsman vulnerability profile computed across every OTHER match."""
    wickets = df[df["is_wicket"]]

    dismissal_features = _leakage_free_rate(df, wickets, "dismissal_type", DISMISSAL_TYPES)
    length_features = _leakage_free_rate(
        df, wickets, "ball_length", tuple(sorted(wickets["ball_length"].dropna().unique().tolist() or ["unknown"]))
    )
    line_features = _leakage_free_rate(
        df, wickets, "ball_line", tuple(sorted(wickets["ball_line"].dropna().unique().tolist() or ["unknown"]))
    )
    df = pd.concat([df, dismissal_features, length_features, line_features], axis=1)

    df["hist_phase_avg"] = _historical_average(df, wickets, group_cols=["batsman", "phase"])
    df["hist_avg_under_pressure"] = _historical_average(
        df, wickets, group_cols=["batsman"], pressure_filter=True
    )
    df["hist_avg_normal"] = _historical_average(
        df, wickets, group_cols=["batsman"], pressure_filter=False
    )
    return df


def _historical_average(
    df: pd.DataFrame,
    wickets: pd.DataFrame,
    group_cols: list[str],
    pressure_filter: bool | None = None,
) -> pd.Series:
    """Batting average (runs / dismissals) in other matches, optionally split by pressure."""
    runs_source = df
    dismissals_source = wickets

    if pressure_filter is not None:
        mask_df = df["pressure_index"] > UNDER_PRESSURE_THRESHOLD
        mask_wickets = wickets["pressure_index"] > UNDER_PRESSURE_THRESHOLD
        if not pressure_filter:
            mask_df = ~mask_df
            mask_wickets = ~mask_wickets
        runs_source = df[mask_df]
        dismissals_source = wickets[mask_wickets]

    runs_by_group = runs_source.groupby(group_cols)["total_runs"].sum()
    runs_by_group_match = runs_source.groupby(group_cols + ["match_id"])["total_runs"].sum()
    dismissals_by_group = dismissals_source.groupby(group_cols).size()
    dismissals_by_group_match = dismissals_source.groupby(group_cols + ["match_id"]).size()

    row_keys = df[group_cols + ["match_id"]]
    total_runs = row_keys.set_index(group_cols)[[]].join(runs_by_group.rename("total"), how="left")["total"]
    match_runs = row_keys.merge(
        runs_by_group_match.rename("match_total").reset_index(), on=group_cols + ["match_id"], how="left"
    )["match_total"]
    total_dismissals = row_keys.set_index(group_cols)[[]].join(
        dismissals_by_group.rename("total"), how="left"
    )["total"]
    match_dismissals = row_keys.merge(
        dismissals_by_group_match.rename("match_total").reset_index(), on=group_cols + ["match_id"], how="left"
    )["match_total"]

    other_runs = (total_runs.to_numpy(dtype=float) - np.nan_to_num(match_runs.to_numpy(dtype=float)))
    other_runs = np.nan_to_num(other_runs, nan=0.0)
    other_dismissals = np.nan_to_num(total_dismissals.to_numpy(dtype=float)) - np.nan_to_num(
        match_dismissals.to_numpy(dtype=float)
    )
    other_dismissals = np.nan_to_num(other_dismissals, nan=0.0)

    safe_divisor = np.where(other_dismissals > 0, other_dismissals, 1.0)
    average = np.where(other_dismissals > 0, other_runs / safe_divisor, other_runs)
    return pd.Series(average, index=df.index)


def add_encodings(df: pd.DataFrame) -> pd.DataFrame:
    df["ball_length_encoded"] = df["ball_length"].map(BALL_LENGTH_ENCODING).fillna(UNKNOWN_ENCODING).astype(int)
    df["ball_line_encoded"] = df["ball_line"].map(BALL_LINE_ENCODING).fillna(UNKNOWN_ENCODING).astype(int)
    return df


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    df["will_dismiss"] = df["is_wicket"].astype(int)
    df["dismissal_type_encoded"] = (
        df["dismissal_type"].map(DISMISSAL_TYPE_ENCODING).fillna(UNKNOWN_ENCODING).astype(int)
    )
    return df


def build_features(deliveries: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Run the full feature engineering pipeline on parsed deliveries."""
    logger = logger or get_logger(__name__)
    if deliveries.empty:
        logger.warning("No deliveries to build features from.")
        return deliveries

    df = deliveries.copy()
    df["is_wicket"] = df["is_wicket"].astype(bool)
    df = _sort_deliveries(df)

    df = add_phase(df)
    df = add_batsman_rolling_features(df)
    df = add_bowler_rolling_features(df)
    df = add_match_context_features(df)
    df = add_historical_batsman_features(df)
    df = add_encodings(df)
    df = add_targets(df)

    logger.info("Built features for %s deliveries", len(df))
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Engineer ML features from parsed deliveries.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = get_logger(__name__)

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        return 1

    deliveries = pd.read_csv(args.input)
    features = build_features(deliveries, logger=logger)
    if features.empty:
        return 1

    csv_path = write_frame(features, args.output.with_suffix(""))
    logger.info("Wrote feature table to %s (+ .parquet)", csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
