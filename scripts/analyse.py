"""Pretty-print a CricXAI recommendation for one batsman / situation.

Talks to a running API (default http://127.0.0.1:8001). Handy for picking
players to analyse without touching Swagger or curl.

Examples::

    py -3.13 scripts/analyse.py --list
    py -3.13 scripts/analyse.py "Virat Kohli" --bowler pace_right_arm \
        --innings 2 --over 43 --ball 2 --score 271 --wickets 6 --target 322
    py -3.13 scripts/analyse.py "Babar Azam" --bowler left_arm_spin \
        --over 24 --score 128 --wickets 2
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8001"


def _get(base: str, path: str):
    with urllib.request.urlopen(base + path) as r:
        return json.load(r)


def _post(base: str, path: str, body: dict):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def list_batsmen(base: str, query: str | None) -> int:
    q = f"?limit=200&q={urllib.parse.quote(query)}" if query else "?limit=200"
    rows = _get(base, "/v1/batsmen" + q)["batsmen"]
    for b in rows:
        print(f"  {b['name']:<26} {b['id']:<34} balls={b['balls']:>4}  outs={b['dismissals']:>2}")
    print(f"\n{len(rows)} batsmen")
    return 0


def analyse(base: str, args: argparse.Namespace) -> int:
    match = {
        "innings": args.innings,
        "over": args.over,
        "ball_in_over": args.ball,
        "score": args.score,
        "wickets": args.wickets,
    }
    if args.innings == 2:
        if args.target is None:
            print("--target is required when --innings 2", file=sys.stderr)
            return 2
        match["target"] = args.target

    body = {
        "match": match,
        "batsman": args.batsman,
        "bowler_type": args.bowler,
        "options": {"top_k": args.top_k},
    }
    try:
        r = _post(base, "/v1/recommendation", body)
    except urllib.error.HTTPError as exc:
        print(f"API error {exc.code}: {exc.read().decode()[:300]}", file=sys.stderr)
        return 1

    s = r["situation"]
    tgt = f"  chasing {match['target']}" if match.get("target") else ""
    print("=" * 78)
    print(f"{s['batsman']}  vs  {args.bowler}")
    print(f"over {args.over}.{args.ball}   {args.score}/{args.wickets}{tgt}   "
          f"phase={s['phase']}  pressure={s['pressure_index']}  "
          f"low_sample={s['low_sample']}   model {r['model_version']}")
    print("-" * 78)
    for it in r["recommendations"]:
        print(f"  #{it['rank']}  {it['label']:<26}  P(wicket) {it['dismissal_probability'] * 100:4.1f}%   "
              f"E[runs] {it['expected_runs']:.2f}   most likely: {it['dismissal_type_top']:<8}  "
              f"[{it['confidence']}]")
        print(f"        field  : {it['field_label']}")
        for rs in it["reasons"]:
            print(f"        reason : {rs}")
        print()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CricXAI recommendation CLI")
    p.add_argument("batsman", nargs="?", help="batsman name, e.g. \"Virat Kohli\"")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--list", action="store_true", help="list available batsmen and exit")
    p.add_argument("--bowler", default="pace_right_arm",
                   choices=["pace_right_arm", "pace_left_arm", "off_spin", "leg_spin", "left_arm_spin"])
    p.add_argument("--innings", type=int, default=1, choices=[1, 2])
    p.add_argument("--over", type=int, default=20)
    p.add_argument("--ball", type=int, default=1)
    p.add_argument("--score", type=int, default=100)
    p.add_argument("--wickets", type=int, default=2)
    p.add_argument("--target", type=int, default=None)
    p.add_argument("--top-k", type=int, default=3)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.list or not args.batsman:
        return list_batsmen(args.base, args.batsman)
    return analyse(args.base, args)


if __name__ == "__main__":
    raise SystemExit(main())
