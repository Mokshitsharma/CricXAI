"""API contract tests against the FastAPI TestClient."""

from __future__ import annotations


def test_health_and_ready(api_client):
    assert api_client.get("/healthz").json() == {"status": "ok"}
    ready = api_client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["models_loaded"] is True


def test_reference_enums(api_client):
    body = api_client.get("/v1/reference").json()
    assert "yorker" in body["ball_lengths"]
    assert "pace_right_arm" in body["bowler_types"]
    assert set(body) == {
        "phases", "ball_lengths", "ball_lines",
        "bowler_types", "dismissal_types", "shot_types",
    }


def test_batsmen_list_and_profile(api_client):
    listing = api_client.get("/v1/batsmen?limit=5").json()["batsmen"]
    assert listing
    bid = listing[0]["id"]
    profile = api_client.get(f"/v1/batsmen/{bid}/profile")
    assert profile.status_code == 200
    body = profile.json()
    assert body["id"] == bid
    assert "dismissal_type_pct" in body
    assert "ball_length_pct" in body


def test_teams_and_filtered_player_list(api_client):
    teams = api_client.get("/v1/teams").json()["teams"]
    assert teams and isinstance(teams, list)

    team = teams[0]
    listed = api_client.get(f"/v1/batsmen?team={team}&since=2000-01-01&limit=50").json()["batsmen"]
    assert listed
    assert all(p["team"] == team for p in listed)
    assert {"id", "name", "team", "balls", "dismissals"} <= set(listed[0])

    # a future cutoff filters everyone out
    empty = api_client.get("/v1/batsmen?since=2999-01-01").json()["batsmen"]
    assert empty == []


def test_bowler_list_head_to_head_and_team_squad(api_client):
    teams = api_client.get("/v1/teams?since=2000-01-01").json()["teams"]
    assert teams
    team = teams[0]

    bowlers = api_client.get(f"/v1/batsmen?team={team}&since=2000-01-01&role=bowler").json()["batsmen"]
    assert bowlers and "wickets" in bowlers[0]

    bats = api_client.get(f"/v1/batsmen?team={team}&since=2000-01-01").json()["batsmen"]
    h2h = api_client.get(
        f"/v1/matchup?batsman={bats[0]['id']}&bowler={bowlers[0]['id']}"
    ).json()
    assert {"balls", "runs", "dismissals", "strike_rate", "dismissal_breakdown"} <= set(h2h)

    squad = api_client.get(f"/v1/team/{team}/squad?since=2000-01-01").json()["players"]
    assert squad
    assert {"id", "name", "role", "rating", "batting", "bowling"} <= set(squad[0])
    assert squad[0]["rating"] >= squad[-1]["rating"]  # sorted by rating desc

    tm = api_client.get(f"/v1/team-matchup?a={teams[0]}&b={teams[-1]}").json()
    assert {"played", "team_a_wins", "team_b_wins", "team_a_win_pct"} <= set(tm)


def test_unknown_batsman_profile_404(api_client):
    r = api_client.get("/v1/batsmen/player-nobody-here/profile")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_recommendation_happy_path(api_client):
    bid = api_client.get("/v1/batsmen?limit=1").json()["batsmen"][0]["id"]
    body = {
        "match": {"innings": 2, "over": 43, "ball_in_over": 2,
                  "score": 271, "wickets": 6, "target": 322},
        "batsman_id": bid,
        "bowler_type": "pace_right_arm",
        "options": {"top_k": 3},
    }
    r = api_client.post("/v1/recommendation", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["situation"]["phase"] == "death"
    assert j["situation"]["pressure_index"] > 0
    assert len(j["recommendations"]) == 3
    top = j["recommendations"][0]
    assert top["rank"] == 1
    assert 0 <= top["dismissal_probability"] <= 1
    assert top["reasons"]
    assert top["field_positions"]
    assert "X-Request-Id" in r.headers


def test_recommendation_unknown_batsman_404(api_client):
    body = {
        "match": {"innings": 1, "over": 10, "score": 50, "wickets": 1},
        "batsman": "Nobody McNoface",
        "bowler_type": "off_spin",
    }
    r = api_client.post("/v1/recommendation", json=body)
    assert r.status_code == 404


def test_recommendation_bad_over_400(api_client):
    bid = api_client.get("/v1/batsmen?limit=1").json()["batsmen"][0]["id"]
    body = {
        "match": {"innings": 1, "over": 77, "score": 50, "wickets": 1},
        "batsman_id": bid,
        "bowler_type": "off_spin",
    }
    r = api_client.post("/v1/recommendation", json=body)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_recommendation_missing_target_400(api_client):
    bid = api_client.get("/v1/batsmen?limit=1").json()["batsmen"][0]["id"]
    body = {
        "match": {"innings": 2, "over": 20, "score": 100, "wickets": 2},
        "batsman_id": bid,
        "bowler_type": "off_spin",
    }
    r = api_client.post("/v1/recommendation", json=body)
    assert r.status_code == 400


def test_predict_dismissal(api_client):
    bid = api_client.get("/v1/batsmen?limit=1").json()["batsmen"][0]["id"]
    body = {
        "match": {"innings": 1, "over": 30, "score": 160, "wickets": 4},
        "batsman_id": bid,
        "bowler_type": "leg_spin",
        "length": "good",
        "line": "off_stump",
    }
    r = api_client.post("/v1/predict/dismissal", json=body)
    assert r.status_code == 200, r.text
    pred = r.json()["prediction"]
    assert pred["length"] == "good" and pred["line"] == "off_stump"


def test_match_timeline(api_client):
    mid = api_client.get("/v1/matches?limit=1").json()["matches"][0]["match_id"]
    r = api_client.get(f"/v1/matches/{mid}/timeline")
    assert r.status_code == 200
    assert r.json()["deliveries"]
