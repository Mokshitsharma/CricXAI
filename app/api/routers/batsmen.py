"""Batsman search and vulnerability profile."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["batsmen"])


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Data store not loaded.")
    return store


@router.get("/teams")
def list_teams(
    request: Request,
    since: str | None = Query(default=None, description="only teams active on/after this ISO date"),
) -> dict:
    return {"teams": _store(request).list_teams(since=since)}


@router.get("/batsmen")
def list_batsmen(
    request: Request,
    q: str | None = Query(default=None, description="name substring"),
    team: str | None = Query(default=None, description="filter to one team"),
    since: str | None = Query(
        default=None, description="min match date, ISO YYYY-MM-DD (recency filter)"
    ),
    role: str = Query(default="batter", pattern="^(batter|bowler)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    store = _store(request)
    if team or since or role == "bowler":
        return {
            "batsmen": store.list_players(
                query=q, team=team, since=since, limit=limit, role=role
            )
        }
    return {"batsmen": store.list_batsmen(query=q, limit=limit)}


@router.get("/team/{team}/squad")
def team_squad(
    request: Request,
    team: str,
    since: str | None = Query(default=None, description="min match date, ISO YYYY-MM-DD"),
) -> dict:
    players = _store(request).team_squad(team, since=since)
    if not players:
        raise HTTPException(status_code=404, detail=f"No players for team: {team}")
    return {"team": team, "players": players}


@router.get("/team-matchup")
def team_matchup(
    request: Request,
    a: str = Query(description="team A"),
    b: str = Query(description="team B"),
    since: str | None = Query(default=None, description="min match date, ISO YYYY-MM-DD"),
) -> dict:
    return _store(request).team_matchup(a, b, since=since)


@router.get("/matchup")
def matchup(
    request: Request,
    batsman: str = Query(description="batsman id or name"),
    bowler: str = Query(description="bowler id or name"),
    since: str | None = Query(default=None, description="min match date, ISO YYYY-MM-DD"),
) -> dict:
    store = _store(request)
    bat = store.resolve_batsman(batsman, batsman)
    bowl = store.resolve_batsman(bowler, bowler)  # same id/name index covers bowlers
    if bat is None:
        raise HTTPException(status_code=404, detail=f"Unknown batsman: {batsman}")
    if bowl is None:
        raise HTTPException(status_code=404, detail=f"Unknown bowler: {bowler}")
    return store.head_to_head(bat, bowl, since=since)


@router.get("/batsmen/{batsman_id}/profile")
def batsman_profile(request: Request, batsman_id: str) -> dict:
    store = _store(request)
    name = store.resolve_batsman(batsman_id, None)
    if name is None:
        raise HTTPException(status_code=404, detail=f"Unknown batsman: {batsman_id}")
    profile = store.batsman_profile(name)
    if not profile:
        raise HTTPException(status_code=422, detail="No data for this batsman.")
    return profile
