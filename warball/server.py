"""
Local web server for the Classic Mode draft UI (web/).

Serves the static page plus a small JSON API backed by the same DraftPool and
season engine the CLI uses, so the browser never does any of the math itself:

  GET  /api/wheel                                 team names + decades, for the reel animation
  GET  /api/spin?open=C,OF,SP&exclude=pid1,pid2   spin until someone fits an open slot
  GET  /api/coach-spin                            spin until the team-decade has a qualified manager
  POST /api/simulate                              {lineup, rotation, bullpen, coach} card ids -> season
  GET  /api/daily?date=YYYY-MM-DD&theme=KEY      the daily challenge (defaults: today in UTC, and that day's theme)
  POST /api/daily/simulate                        {date, picks: [ids], theme?} -> score vs. par + breakdown

Usage:
    python -m warball.server        # then open http://127.0.0.1:8000 (Classic) or /daily.html
"""

import datetime
import json
import os
import random
from dataclasses import asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from warball import season
from warball.constants import BATTER_SEASON_PA, LEAGUE_AVG_RUNS_PER_SEASON, PYTHAGOREAN_EXPONENT, SEASON_GAMES
from warball.daily import DailyChallenge
from warball.draft import DraftPool, Spin
from warball.eligibility import ALL_SLOTS, BULLPEN_SLOTS, LINEUP_SLOTS, ROTATION_SLOTS
from warball.roster import Roster

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", 8000))
MAX_BODY_BYTES = 64 * 1024

FIELD_POSITION_ORDER = ["C", "1B", "2B", "3B", "SS", "OF"]


def _card_id(kind: str, row: dict) -> str:
    return f"{kind}:{row['playerID']}:{row['franchID']}:{row['decade']}"


def hitter_card(row: dict) -> dict:
    fielding = [p for p in FIELD_POSITION_ORDER if p in row["slots"]]
    positions = ["OF/CF" if p == "OF" and row["cf"] else p for p in fielding] or ["DH"]
    return {
        "id": _card_id("h", row),
        "kind": "hitter",
        "playerID": row["playerID"],
        "name": row["name"],
        "last": row["last"],
        "year": int(row["yearID"]),
        "positions": positions,
        "slots": sorted(row["slots"]),
        "stat": {"label": "WAR", "value": round(float(row["WAR"]), 1)},
    }


def pitcher_card(row: dict) -> dict:
    return {
        "id": _card_id("p", row),
        "kind": "pitcher",
        "playerID": row["playerID"],
        "name": row["name"],
        "last": row["last"],
        "year": int(row["yearID"]),
        "positions": [role for role in ("SP", "RP") if role in row["slots"]],
        "slots": sorted(row["slots"]),
        "stat": {"label": "FIP", "value": round(float(row["FIP"]), 2)},
    }


def coach_card(row: dict) -> dict:
    first, last = int(row["first_year"]), int(row["last_year"])
    return {
        "id": _card_id("c", row),
        "kind": "coach",
        "playerID": row["playerID"],
        "name": row["name"],
        "last": row["last"],
        "years": str(first) if first == last else f"{first}-{last}",
        "record": f"{int(row['W'])}-{int(row['L'])}",
        "expectedWins": round(float(row["expected_W"]), 1),
        "positions": ["MGR"],
        "stat": {"label": "W vs PYTH", "value": round(float(row["wins_vs_pythag"]), 1)},
    }


def _spin_payload(spin: Spin, cards: list[dict]) -> dict:
    return {"team": spin.team_name, "era": f"{spin.decade}s", "cards": cards}


class DraftApi:
    def __init__(self, pool: DraftPool):
        self.pool = pool
        self.rng = random.Random()
        self.cards = {_card_id("h", r): r for r in pool.hitters.to_dict("records")}
        self.cards |= {_card_id("p", r): r for r in pool.pitchers.to_dict("records")}
        self.coaches = {_card_id("c", r): r for r in pool.managers.to_dict("records")}
        self.daily = DailyChallenge()

    def wheel(self) -> dict:
        return {
            "teams": sorted(self.pool.wheel["team_name"].unique().tolist()),
            "eras": [f"{d}s" for d in sorted(self.pool.wheel["decade"].unique().tolist())],
        }

    def spin(self, open_slots: set, exclude: set) -> dict:
        if not open_slots & set(ALL_SLOTS):
            raise ValueError("No open slots to draft into")
        while True:
            spin = self.pool.spin(self.rng)
            hitters, pitchers = self.pool.roster_for(spin, exclude)
            cards = [hitter_card(r) for r in hitters.to_dict("records") if r["slots"] & open_slots]
            fitting_pitchers = [r for r in pitchers.to_dict("records") if r["slots"] & open_slots]
            cards += [pitcher_card(r) for r in sorted(fitting_pitchers, key=lambda r: r["FIP"])]
            if cards:
                return _spin_payload(spin, cards)

    def coach_spin(self) -> dict:
        while True:
            spin = self.pool.spin(self.rng)
            managers = self.pool.managers_for(spin)
            if not managers.empty:
                return _spin_payload(spin, [coach_card(r) for r in managers.to_dict("records")])

    def simulate(self, body: dict) -> dict:
        ids = list(body["lineup"]) + list(body["rotation"]) + list(body["bullpen"])
        if len(body["lineup"]) != len(LINEUP_SLOTS) or len(body["rotation"]) != ROTATION_SLOTS or len(body["bullpen"]) != BULLPEN_SLOTS:
            raise ValueError("Roster must have 9 hitters, 5 starters, and 3 relievers")

        roster = Roster()
        for label, card_id in zip(ALL_SLOTS, ids):
            if card_id not in self.cards:
                raise ValueError(f"Unknown card {card_id}")
            roster.assign(self.cards[card_id], label)

        if body["coach"] not in self.coaches:
            raise ValueError(f"Unknown coach {body['coach']}")
        coach = self.coaches[body["coach"]]

        result = season.simulate(roster, coach_wins=float(coach["wins_vs_pythag"]))
        return {
            "result": asdict(result),
            "coach": coach_card(coach),
            "constants": {
                "leagueAvgRuns": LEAGUE_AVG_RUNS_PER_SEASON,
                "batterSeasonPA": BATTER_SEASON_PA,
                "pythagExponent": PYTHAGOREAN_EXPONENT,
                "seasonGames": SEASON_GAMES,
            },
        }


def _daily_date(value: str | None) -> datetime.date:
    """A challenge date from the client, or today in UTC so everyone shares the same puzzle."""
    return datetime.date.fromisoformat(value) if value else datetime.datetime.now(datetime.timezone.utc).date()


class Handler(SimpleHTTPRequestHandler):
    api: DraftApi

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return super().do_GET()

        params = parse_qs(url.query)
        split = lambda key: {v for v in params.get(key, [""])[0].split(",") if v}
        routes = {
            "/api/wheel": lambda: self.api.wheel(),
            "/api/spin": lambda: self.api.spin(split("open"), split("exclude")),
            "/api/coach-spin": lambda: self.api.coach_spin(),
            "/api/daily": lambda: self.api.daily.challenge(
                _daily_date(params.get("date", [None])[0]), params.get("theme", [None])[0]
            ),
        }
        self._respond(routes.get(url.path))

    def do_POST(self):
        routes = {
            "/api/simulate": lambda body: self.api.simulate(body),
            "/api/daily/simulate": lambda body: self.api.daily.simulate(
                _daily_date(body["date"]), list(body.get("picks", body.get("staff", []))), body.get("theme")
            ),
        }
        route = routes.get(urlparse(self.path).path)
        if route is None:
            return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return self._send_json({"error": "Request too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        body = self.rfile.read(length)
        self._respond(lambda: route(json.loads(body)))

    def _respond(self, handler):
        if handler is None:
            return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        try:
            self._send_json(handler())
        except (ValueError, KeyError, TypeError) as err:
            self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    print("Loading draft pool (about 15 seconds)...", flush=True)
    Handler.api = DraftApi(DraftPool())
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"WARBall running at http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
