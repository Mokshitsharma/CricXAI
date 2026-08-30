"""In-memory, CSV-backed data access layer.

Loads ``deliveries.csv``, ``matches.csv`` and ``delivery_features.csv`` once
at startup and answers the read queries the API needs. The interface
(methods on :class:`DataStore`) is what a Postgres implementation will
implement in Phase 3 — keep it small and storage-agnostic.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.features import BASE_FEATURES, historical_feature_columns
from app.utils.file_io import read_frame
from app.utils.logger import get_logger

DEFAULT_PROCESSED_DIR = Path("data/processed")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", str(name).strip().lower()).strip("-")


class DataStore:
    def __init__(self, processed_dir: Path | None = None, logger=None):
        self.logger = logger or get_logger(__name__)
        self.dir = Path(
            processed_dir
            or os.environ.get("CRICXAI_PROCESSED_DIR")
            or DEFAULT_PROCESSED_DIR
        )
        self.deliveries = read_frame(self.dir / "deliveries")
        self.matches = read_frame(self.dir / "matches")
        self.features = read_frame(self.dir / "delivery_features")
        self.deliveries["is_wicket"] = self.deliveries["is_wicket"].astype(bool)
        self.features["is_wicket"] = self.features["is_wicket"].astype(bool)

        # Per-delivery match date (ISO string), for recency filters and the
        # "most recent team" resolution below. Missing in the mock schema.
        date_by_match = (
            dict(zip(self.matches["match_id"].astype(str), self.matches["date"].astype(str), strict=False))
            if "date" in self.matches.columns
            else {}
        )
        self.deliveries["match_date"] = (
            self.deliveries["match_id"].astype(str).map(date_by_match)
        )

        # Bowling team per delivery = the match's other team (needs matches
        # home/away + per-ball batting_team; absent in some schemas).
        if "batting_team" in self.deliveries.columns and {
            "home_team", "away_team"
        } <= set(self.matches.columns):
            mid = self.deliveries["match_id"].astype(str)
            home = mid.map(dict(zip(self.matches["match_id"].astype(str), self.matches["home_team"], strict=False)))
            away = mid.map(dict(zip(self.matches["match_id"].astype(str), self.matches["away_team"], strict=False)))
            self.deliveries["bowling_team"] = np.where(
                self.deliveries["batting_team"].eq(home), away, home
            )

        self._hist_cols = historical_feature_columns(self.features)
        self._id_to_name: dict[str, str] = {}
        self._name_to_id: dict[str, str] = {}
        both = pd.concat(
            [self.deliveries["batsman"], self.deliveries["bowler"]], ignore_index=True
        ).dropna().unique()
        for name in sorted(both):
            pid = f"player-{slugify(name)}"
            self._id_to_name[pid] = name
            self._name_to_id[name] = pid

        self._batsman_ctx = self._precompute_batsman_context()
        self._feature_means = self._precompute_feature_means()
        self._teams, self._player_team, self._bowler_team = self._precompute_player_directory()
        self.logger.info(
            "DataStore ready: %s deliveries, %s matches, %s batsmen, %s teams",
            len(self.deliveries), len(self.matches), len(self._id_to_name), len(self._teams),
        )

    # -- identity ---------------------------------------------------------
    def resolve_batsman(self, batsman_id: str | None, batsman: str | None) -> str | None:
        if batsman_id and batsman_id in self._id_to_name:
            return self._id_to_name[batsman_id]
        if batsman and batsman in self._name_to_id:
            return batsman
        if batsman:
            pid = f"player-{slugify(batsman)}"
            return self._id_to_name.get(pid)
        return None

    def batsman_id(self, name: str) -> str:
        return self._name_to_id.get(name, f"player-{slugify(name)}")

    # -- batsmen --------------------------------------------------------
    def list_batsmen(self, query: str | None = None, limit: int = 50) -> list[dict]:
        rows = []
        for pid, name in self._id_to_name.items():
            if query and query.lower() not in name.lower():
                continue
            ctx = self._batsman_ctx.get(name, {})
            rows.append(
                {
                    "id": pid,
                    "name": name,
                    "balls": int(ctx.get("balls", 0)),
                    "dismissals": int(ctx.get("dismissals", 0)),
                }
            )
        rows.sort(key=lambda r: r["balls"], reverse=True)
        return rows[:limit]

    def list_teams(self, since: str | None = None) -> list[str]:
        """Distinct batting teams (empty for the mock schema). With ``since``
        (ISO date), only teams that have batted on/after that date."""
        if not since or "batting_team" not in self.deliveries.columns:
            return list(self._teams)
        d = self.deliveries
        if not d["match_date"].notna().any():
            return list(self._teams)
        recent = d.loc[d["match_date"].fillna("") >= since, "batting_team"].dropna().unique()
        return sorted(str(t) for t in recent)

    def list_players(
        self,
        query: str | None = None,
        team: str | None = None,
        since: str | None = None,
        limit: int = 200,
        role: str = "batter",
    ) -> list[dict]:
        """Players filtered by team and a minimum match date (ISO
        ``YYYY-MM-DD``). ``role="batter"`` lists everyone who has batted, with
        ``balls`` faced / ``dismissals`` / ``matches`` in the window;
        ``role="bowler"`` lists everyone who has bowled, with ``balls`` bowled
        / ``wickets`` / ``matches``. ``team`` is the most recent team on that
        side (all-time)."""
        d = self.deliveries
        bowler_role = role == "bowler"
        who = "bowler" if bowler_role else "batsman"
        team_col = "bowling_team" if bowler_role else "batting_team"
        team_map = self._bowler_team if bowler_role else self._player_team

        mask = d[who].notna()
        if since and d["match_date"].notna().any():
            mask &= d["match_date"].fillna("") >= since
        if team and team_col in d.columns:
            mask &= d[team_col] == team
        sub = d.loc[mask, [who, "match_id", "outcome", "is_wicket"]]
        if sub.empty:
            return []

        if bowler_role:
            countable = ~sub["outcome"].isin(["wide", "no_ball"])  # legal balls bowled
        else:
            countable = sub["outcome"].ne("wide")  # balls faced
        grouped = sub.assign(
            _n=countable.astype(int), _wkt=sub["is_wicket"].astype(int)
        ).groupby(who)
        agg = grouped.agg(n=("_n", "sum"), wkt=("_wkt", "sum"), matches=("match_id", "nunique"))
        count_key = "wickets" if bowler_role else "dismissals"

        rows = []
        for name, r in agg.iterrows():
            name = str(name)
            if query and query.lower() not in name.lower():
                continue
            rows.append(
                {
                    "id": self.batsman_id(name),
                    "name": name,
                    "team": team_map.get(name) or None,
                    "balls": int(r["n"]),
                    count_key: int(r["wkt"]),
                    "matches": int(r["matches"]),
                }
            )
        rows.sort(key=lambda x: x["balls"], reverse=True)
        return rows[:limit]

    def head_to_head(self, batsman: str, bowler: str, since: str | None = None) -> dict:
        """Real batsman-vs-bowler record from the ball-by-ball data."""
        d = self.deliveries
        mask = (d["batsman"] == batsman) & (d["bowler"] == bowler)
        if since and d["match_date"].notna().any():
            mask &= d["match_date"].fillna("") >= since
        sub = d[mask]

        out = {
            "batsman": batsman, "bowler": bowler, "balls": 0, "runs": 0,
            "dismissals": 0, "strike_rate": 0.0, "dot_pct": 0.0,
            "boundary_pct": 0.0, "dismissal_breakdown": {}, "matches": 0,
            "first_seen": None, "last_seen": None,
        }
        if sub.empty:
            return out

        legal = sub[~sub["outcome"].isin(["wide", "no_ball"])]
        balls = int(len(legal))
        # runs conceded to the batsman (exclude wide/bye/leg_bye rows)
        off_bat = sub[~sub["outcome"].isin(["wide", "bye", "leg_bye"])]
        runs = int(off_bat["total_runs"].fillna(0).sum())
        outs = sub[sub["is_wicket"]]
        if "player_out" in sub.columns:
            outs = outs[outs["player_out"] == batsman]
        dots = int((legal["outcome"] == "dot").sum())
        bdry = int(sub["outcome"].isin(["four", "six"]).sum())

        out.update(
            balls=balls,
            runs=runs,
            dismissals=int(len(outs)),
            strike_rate=round(100.0 * runs / balls, 1) if balls else 0.0,
            dot_pct=round(100.0 * dots / balls, 1) if balls else 0.0,
            boundary_pct=round(100.0 * bdry / balls, 1) if balls else 0.0,
            dismissal_breakdown=outs["dismissal_type"].value_counts().to_dict(),
            matches=int(sub["match_id"].nunique()),
        )
        if "match_date" in sub.columns and sub["match_date"].notna().any():
            out["first_seen"] = str(sub["match_date"].min())
            out["last_seen"] = str(sub["match_date"].max())
        return out

    def team_squad(self, team: str, since: str | None = None) -> list[dict]:
        """A team's players (batted or bowled in the window), each with real
        batting/bowling aggregates, an inferred role, and a 0-100 rating."""
        batters = {p["name"]: p for p in self.list_players(team=team, since=since, limit=500, role="batter")}
        bowlers = {p["name"]: p for p in self.list_players(team=team, since=since, limit=500, role="bowler")}
        d = self.deliveries
        base = d["match_date"].notna().any()

        def bat_runs(name: str) -> int:
            m = (d["batsman"] == name) & (~d["outcome"].isin(["wide", "bye", "leg_bye"]))
            if since and base:
                m &= d["match_date"].fillna("") >= since
            return int(d.loc[m, "total_runs"].fillna(0).sum())

        def bowl_runs(name: str) -> int:
            m = d["bowler"] == name
            if since and base:
                m &= d["match_date"].fillna("") >= since
            return int(d.loc[m, "total_runs"].fillna(0).sum())

        out = []
        for name in sorted(set(batters) | set(bowlers)):
            b = batters.get(name, {})
            w = bowlers.get(name, {})
            bat_b = int(b.get("balls", 0))
            bowl_b = int(w.get("balls", 0))
            # squad membership: a meaningful sample on at least one discipline
            if bat_b < 90 and bowl_b < 90:
                continue
            runs = bat_runs(name) if bat_b else 0
            outs = int(b.get("dismissals", 0))
            conceded = bowl_runs(name) if bowl_b else 0
            wkts = int(w.get("wickets", 0))
            bat_sr = round(100.0 * runs / bat_b, 1) if bat_b else 0.0
            bat_avg = round(runs / outs, 1) if outs else (float(runs) if runs else 0.0)
            bowl_econ = round(6.0 * conceded / bowl_b, 2) if bowl_b else 0.0
            bowl_avg = round(conceded / wkts, 1) if wkts else 0.0

            is_bowler = bowl_b >= 90
            is_batter = bat_b >= 90
            role = "allrounder" if (is_bowler and is_batter and bat_avg >= 22 and wkts >= 5) else (
                "bowler" if is_bowler and not (is_batter and bat_avg >= 28) else "batter"
            )
            # gentle, sample-capped scores so the top of a squad still spreads out
            capped_avg = min(bat_avg, 62.0)
            bat_score = capped_avg * 1.05 + bat_sr * 0.14 if bat_b else 0.0  # ~50@90 -> 65; ~40@110 -> 57
            bowl_score = (
                max(0.0, 112.0 - min(bowl_avg, 60.0) * 1.35 - bowl_econ * 4.6) if wkts else 0.0
            )
            if role == "allrounder":
                rating = 0.55 * bat_score + 0.55 * bowl_score + 6
            elif role == "bowler":
                rating = bowl_score
            else:
                rating = bat_score
            rating = round(min(100.0, max(1.0, rating)), 1)

            out.append({
                "id": self.batsman_id(name), "name": name, "role": role, "rating": rating,
                "batting": {"balls": bat_b, "runs": runs, "outs": outs, "sr": bat_sr, "avg": bat_avg},
                "bowling": {"balls": bowl_b, "runs": conceded, "wickets": wkts, "econ": bowl_econ, "avg": bowl_avg},
            })
        out.sort(key=lambda p: p["rating"], reverse=True)
        return out

    def team_matchup(self, team_a: str, team_b: str, since: str | None = None) -> dict:
        """Historical head-to-head result record between two teams."""
        m = self.matches
        res = {"team_a": team_a, "team_b": team_b, "played": 0,
               "team_a_wins": 0, "team_b_wins": 0, "no_result": 0, "team_a_win_pct": 50.0}
        if not {"home_team", "away_team", "result"}.issubset(m.columns):
            return res
        pair = ((m["home_team"] == team_a) & (m["away_team"] == team_b)) | (
            (m["home_team"] == team_b) & (m["away_team"] == team_a)
        )
        if since and "date" in m.columns:
            pair &= m["date"].fillna("") >= since
        sub = m[pair]
        a_wins = b_wins = nr = 0
        for r in sub["result"].fillna(""):
            if team_a in r and "won" in r:
                a_wins += 1
            elif team_b in r and "won" in r:
                b_wins += 1
            else:
                nr += 1
        played = int(len(sub))
        res.update(played=played, team_a_wins=a_wins, team_b_wins=b_wins, no_result=nr)
        decided = a_wins + b_wins
        if decided:
            res["team_a_win_pct"] = round(100.0 * a_wins / decided, 1)
        return res

    def batsman_feature_context(self, name: str) -> dict[str, float]:
        return self._batsman_ctx.get(name, {}).get("features", {})

    def batsman_dismissals(self, name: str) -> int:
        return int(self._batsman_ctx.get(name, {}).get("dismissals", 0))

    def batsman_profile(self, name: str) -> dict:
        ctx = self._batsman_ctx.get(name)
        if ctx is None:
            return {}
        feats = ctx["features"]

        def pull(prefix: str) -> dict[str, float]:
            out = {}
            for col in self._hist_cols:
                if col.startswith(prefix):
                    key = col[len(prefix):-len("_pct")] if col.endswith("_pct") else col[len(prefix):]
                    out[key] = round(float(feats.get(col, 0.0)), 1)
            return out

        wk = self.deliveries[(self.deliveries["batsman"] == name) & self.deliveries["is_wicket"]]
        return {
            "id": self.batsman_id(name),
            "name": name,
            "balls_faced": int(ctx.get("balls", 0)),
            "dismissals": int(ctx.get("dismissals", 0)),
            "matches": int(ctx.get("matches", 0)),
            "low_sample": int(ctx.get("dismissals", 0)) < 6,
            "dismissal_type_pct": pull("hist_dismissal_type_"),
            "ball_length_pct": pull("hist_ball_length_"),
            "ball_line_pct": pull("hist_ball_line_"),
            "phase_average": round(float(feats.get("hist_phase_avg", 0.0)), 1),
            "average_under_pressure": round(float(feats.get("hist_avg_under_pressure", 0.0)), 1),
            "average_normal": round(float(feats.get("hist_avg_normal", 0.0)), 1),
            "dismissal_count_by_type": wk["dismissal_type"].value_counts().to_dict(),
        }

    # -- matches ------------------------------------------------------
    def list_matches(self, limit: int = 100) -> list[dict]:
        cols = [c for c in ["match_id", "teams", "venue", "date", "result",
                            "innings1_runs", "innings2_runs", "delivery_count"]
                if c in self.matches.columns]
        return self.matches[cols].head(limit).to_dict(orient="records")

    def match_timeline(self, match_id: str) -> list[dict]:
        d = self.deliveries[self.deliveries["match_id"] == match_id].copy()
        if d.empty:
            return []
        d = d.sort_values(["innings", "over", "ball_in_over"], kind="stable")
        cols = ["innings", "over", "ball_in_over", "batsman", "bowler",
                "total_runs", "outcome", "is_wicket", "dismissal_type",
                "ball_length", "ball_line", "text"]
        return d[[c for c in cols if c in d.columns]].to_dict(orient="records")

    # -- model reasons ------------------------------------------------
    def feature_means(self) -> dict[str, float]:
        return self._feature_means

    # -- internals --------------------------------------------------------
    def _precompute_batsman_context(self) -> dict[str, dict]:
        """Per-batsman feature means + ball/dismissal/match counts.

        Two grouped passes (one over the feature table, one over deliveries)
        rather than a per-batsman boolean scan — the latter is O(players x
        rows) and dominates DataStore startup on a full-size dataset.
        """
        feat_cols = [c for c in BASE_FEATURES if c in self.features.columns] + self._hist_cols
        means_by_batsman = self.features.groupby("batsman")[feat_cols].mean(numeric_only=True)

        d = self.deliveries
        counts = (
            d.assign(
                _faced=d["outcome"].ne("wide").astype(int),
                _wkt=d["is_wicket"].astype(int),
            )
            .groupby("batsman")
            .agg(balls=("_faced", "sum"), dismissals=("_wkt", "sum"), matches=("match_id", "nunique"))
        )

        out: dict[str, dict] = {}
        for name, mrow in means_by_batsman.iterrows():
            key = str(name)
            feats = {k: float(v) for k, v in mrow.items() if pd.notna(v)}
            c = counts.loc[name] if name in counts.index else None
            out[key] = {
                "features": feats,
                "balls": int(c["balls"]) if c is not None else 0,
                "dismissals": int(c["dismissals"]) if c is not None else 0,
                "matches": int(c["matches"]) if c is not None else 0,
            }
        return out

    def _precompute_feature_means(self) -> dict[str, float]:
        cols = [c for c in BASE_FEATURES if c in self.features.columns] + self._hist_cols
        means = self.features[cols].mean(numeric_only=True)
        return {k: float(v) for k, v in means.items() if not np.isnan(v)}

    def _precompute_player_directory(
        self,
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        """(sorted team list, {batter -> latest batting team}, {bowler -> latest bowling team})."""
        d = self.deliveries
        if "batting_team" not in d.columns:
            return [], {}, {}
        teams = sorted(t for t in d["batting_team"].dropna().unique())
        dated = "match_date" in d.columns and d["match_date"].notna().any()

        bat = d.dropna(subset=["batsman", "batting_team"])
        if dated:
            bat = bat.sort_values("match_date", kind="stable")
        player_team = {str(k): str(v) for k, v in bat.groupby("batsman")["batting_team"].last().items()}

        bowler_team: dict[str, str] = {}
        if "bowling_team" in d.columns:
            bowl = d.dropna(subset=["bowler", "bowling_team"])
            if dated:
                bowl = bowl.sort_values("match_date", kind="stable")
            bowler_team = {str(k): str(v) for k, v in bowl.groupby("bowler")["bowling_team"].last().items()}

        return teams, player_team, bowler_team


@lru_cache(maxsize=1)
def get_data_store() -> DataStore:
    return DataStore()
