import pandas as pd
import pytest

from scripts.build_features import build_features


def _row(
    match_id,
    innings,
    over,
    ball_in_over,
    batsman,
    bowler,
    total_runs,
    outcome,
    is_wicket=False,
    dismissal_type=None,
    ball_length="unknown",
    ball_line="unknown",
):
    return {
        "match_id": match_id,
        "innings": innings,
        "over": over,
        "ball_in_over": ball_in_over,
        "batsman": batsman,
        "bowler": bowler,
        "text": "",
        "total_runs": total_runs,
        "ball_length": ball_length,
        "ball_line": ball_line,
        "shot_type": "unknown",
        "outcome": outcome,
        "is_wicket": is_wicket,
        "dismissal_type": dismissal_type,
        "player_out": batsman if is_wicket else None,
    }


def test_batsman_rolling_features_never_leak_the_current_ball():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 0, 1, "A", "X", 1, "single"),
            _row("M1", 1, 0, 2, "A", "X", 0, "dot"),
            _row("M1", 1, 0, 3, "A", "X", 4, "four"),
            _row("M1", 1, 0, 4, "A", "X", 0, "wicket", is_wicket=True, dismissal_type="bowled",
                 ball_length="full", ball_line="off_stump"),
        ]
    )
    features = build_features(deliveries)

    assert features.loc[0, "batsman_runs_so_far"] == 0
    assert features.loc[0, "batsman_balls_faced"] == 0
    assert features.loc[1, "batsman_runs_so_far"] == 1
    assert features.loc[1, "batsman_balls_faced"] == 1
    assert features.loc[2, "batsman_runs_so_far"] == 1
    assert features.loc[2, "batsman_balls_faced"] == 2
    assert features.loc[3, "batsman_runs_so_far"] == 5
    assert features.loc[3, "batsman_balls_faced"] == 3

    # strike rate at row 3 (index 2): 1 run off 2 balls so far = 50.0
    assert features.loc[2, "batsman_strike_rate"] == pytest.approx(50.0)
    # dot pct at row 3 (index 2): 1 dot out of 2 balls so far = 50%
    assert features.loc[2, "batsman_dot_pct"] == pytest.approx(50.0)


def test_bowler_rolling_features_never_leak_the_current_ball():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 0, 1, "A", "X", 1, "single"),
            _row("M1", 1, 0, 2, "B", "X", 4, "four"),
            _row("M1", 1, 0, 3, "A", "X", 0, "dot"),
        ]
    )
    features = build_features(deliveries)

    assert features.loc[0, "bowler_balls_bowled"] == 0
    assert features.loc[1, "bowler_balls_bowled"] == 1
    assert features.loc[2, "bowler_balls_bowled"] == 2
    # economy at row 3 (index 2): 5 runs off 2 balls (0.333 overs) so far
    assert features.loc[2, "bowler_economy"] == pytest.approx(5 / (2 / 6))


def test_pressure_index_first_ball_of_chase():
    deliveries = pd.DataFrame(
        [
            # Innings 1 totals 100 runs -> target = 101 for innings 2.
            _row("M1", 1, 49, 6, "C", "Y", 100, "six"),
            # First ball of the chase: nothing scored, no overs gone.
            _row("M1", 2, 0, 1, "A", "X", 0, "dot"),
        ]
    )
    features = build_features(deliveries)
    chase_row = features[(features["match_id"] == "M1") & (features["innings"] == 2)].iloc[0]

    # required_run_rate = (101 - 0) / 50 = 2.02; current_run_rate = 0 (no overs bowled yet)
    assert chase_row["pressure_index"] == pytest.approx(101 / 50)


def test_pressure_index_capped_at_ten():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 49, 6, "C", "Y", 300, "six"),
            _row("M1", 2, 45, 1, "A", "X", 0, "dot", is_wicket=False),
        ]
    )
    features = build_features(deliveries)
    chase_row = features[(features["match_id"] == "M1") & (features["innings"] == 2)].iloc[0]
    assert chase_row["pressure_index"] <= 10.0


def test_pressure_index_floored_at_zero_for_a_cruising_chase():
    # Innings 1 all out for 60 -> tiny target; the chase romps it so
    # required_run_rate << current_run_rate and raw pressure goes negative.
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 20, 6, "C", "Y", 60, "six"),
            _row("M1", 2, 5, 1, "A", "X", 6, "six"),
            _row("M1", 2, 5, 2, "A", "X", 6, "six"),
        ]
    )
    features = build_features(deliveries)
    chase = features[(features["match_id"] == "M1") & (features["innings"] == 2)]
    assert (chase["pressure_index"] >= 0.0).all()


def test_strike_rate_is_clipped():
    from scripts.build_features import STRIKE_RATE_CAP

    # 6 runs off the first ball -> raw rolling SR would be 600 on ball 2.
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 0, 1, "A", "X", 6, "six"),
            _row("M1", 1, 0, 2, "A", "X", 0, "dot"),
        ]
    )
    features = build_features(deliveries)
    assert features["batsman_strike_rate"].max() <= STRIKE_RATE_CAP


def test_innings_one_has_zero_pressure_index():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 0, 1, "A", "X", 1, "single"),
            _row("M1", 1, 0, 2, "A", "X", 4, "four"),
        ]
    )
    features = build_features(deliveries)
    assert (features["pressure_index"] == 0.0).all()


def test_encodings_map_unknown_to_negative_one():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 5, 1, "A", "X", 0, "dot", ball_length="unknown", ball_line="unknown"),
            _row("M1", 1, 5, 2, "A", "X", 4, "four", ball_length="full", ball_line="off_stump"),
        ]
    )
    features = build_features(deliveries)
    assert features.loc[0, "ball_length_encoded"] == -1
    assert features.loc[0, "ball_line_encoded"] == -1
    assert features.loc[1, "ball_length_encoded"] == 1  # "full" is index 1 in BALL_LENGTHS
    assert features.loc[1, "dismissal_type_encoded"] == -1  # not a wicket ball


def test_phase_encoding_from_over_number():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 3, 1, "A", "X", 0, "dot"),
            _row("M1", 1, 25, 1, "A", "X", 0, "dot"),
            _row("M1", 1, 45, 1, "A", "X", 0, "dot"),
        ]
    )
    features = build_features(deliveries)
    assert features.loc[0, "phase"] == "powerplay"
    assert features.loc[1, "phase"] == "middle"
    assert features.loc[2, "phase"] == "death"


def test_will_dismiss_target():
    deliveries = pd.DataFrame(
        [
            _row("M1", 1, 0, 1, "A", "X", 0, "wicket", is_wicket=True, dismissal_type="bowled"),
            _row("M1", 1, 0, 2, "B", "X", 1, "single"),
        ]
    )
    features = build_features(deliveries)
    assert features.loc[0, "will_dismiss"] == 1
    assert features.loc[1, "will_dismiss"] == 0


def test_historical_batsman_dismissal_features_exclude_current_match():
    deliveries = pd.DataFrame(
        [
            # Batsman A dismissed "bowled" in match M1.
            _row("M1", 1, 0, 1, "A", "X", 0, "wicket", is_wicket=True, dismissal_type="bowled"),
            # Batsman A dismissed "caught" in match M2.
            _row("M2", 1, 0, 1, "A", "X", 0, "wicket", is_wicket=True, dismissal_type="caught"),
        ]
    )
    features = build_features(deliveries)

    m1_row = features[features["match_id"] == "M1"].iloc[0]
    m2_row = features[features["match_id"] == "M2"].iloc[0]

    # M1's row should reflect ONLY M2's history: 100% caught, 0% bowled.
    assert m1_row["hist_dismissal_type_caught_pct"] == pytest.approx(100.0)
    assert m1_row["hist_dismissal_type_bowled_pct"] == pytest.approx(0.0)

    # M2's row should reflect ONLY M1's history: 100% bowled, 0% caught.
    assert m2_row["hist_dismissal_type_bowled_pct"] == pytest.approx(100.0)
    assert m2_row["hist_dismissal_type_caught_pct"] == pytest.approx(0.0)


def test_empty_dataframe_does_not_crash():
    empty = pd.DataFrame(
        columns=[
            "match_id", "innings", "over", "ball_in_over", "batsman", "bowler",
            "text", "total_runs", "ball_length", "ball_line", "shot_type",
            "outcome", "is_wicket", "dismissal_type", "player_out",
        ]
    )
    result = build_features(empty)
    assert result.empty
