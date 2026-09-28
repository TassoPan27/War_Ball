"""
Daily Mode Theme C: Great Pitchers. One modern ace vs. a lineup you draft.

Statcast-era only (2015-2024), because pitch-type data doesn't exist before
it. The build (python -m warball.aces, after python -m warball.statcast):

  - aces: the ACES pitchers with at least ACE_MIN_BF plate appearances who
    allow the lowest wOBA to a league-average hitter (fitted model, so small
    samples can't sneak in)
  - signature pitch: of the pitch groups ending at least SIGNATURE_MIN_USAGE
    of his plate appearances, the one where he beats the league by the most
    wOBA. Chosen from the data, not from scouting reports; phase4_check
    confirms it matches the reports for Kershaw's curveball.
  - hitter pool: every hitter with at least HITTER_MIN_PA plate appearances
  - par per ace: PAR_SAMPLES random 9-man lineups from the hitter pool

Each day draws one ace and a POOL_SIZE-hitter draft pool. You draft
LINEUP_SIZE hitters; they bat in the order drafted, TIMES_THROUGH times
through the order, every plate appearance a pitch-group-mixed log5 matchup
(arsenal.py) fed to the same base-out engine as the other themes. The score
is expected runs scored: higher is better, and par is to be beaten from
above.
"""

import datetime
import json
import random

import numpy as np
import pandas as pd

from warball import arsenal, matchup, par, runs, statcast
from warball.arsenal import COUNT_COLUMNS, GROUP_NAMES, GROUPS, OUTCOMES
from warball.data import PROCESSED_DIR

THEME_LABEL = "GREAT PITCHERS"
CHALLENGE_FILE = PROCESSED_DIR / "daily_aces.json"

ACE_MIN_BF = 3000  # ~5 full seasons as a starter
ACES = 8
SIGNATURE_MIN_USAGE = 0.15
HITTER_MIN_PA = 1500  # ~3 seasons as a regular
POOL_SIZE = 20
LINEUP_SIZE = 9
TIMES_THROUGH = 3


def _players(df: pd.DataFrame, min_pa: int) -> dict:
    """Long per-group counts -> {player id: {name, years, PA, groups: {group: counts}}} for players with enough PA."""
    players = {}
    for pid, rows in df.groupby("player"):
        total = int(rows["PA"].sum())
        if total < min_pa:
            continue
        first = rows.iloc[0]
        players[str(pid)] = {
            "name": first["name"],
            "years": f"{int(first['first_year'])}-{int(first['last_year'])}",
            "PA": total,
            "groups": {r["group"]: {c: int(r[c]) for c in (*COUNT_COLUMNS, "swings", "whiffs")} for _, r in rows.iterrows()},
        }
    return players


def _whiff_rate(counts: dict | None) -> float | None:
    return counts["whiffs"] / counts["swings"] if counts and counts["swings"] else None


def group_woba(batter, pitcher, env: arsenal.ArsenalEnv, g: str) -> float:
    """Modeled wOBA on plate appearances ending on pitch group g."""
    return arsenal.woba(matchup.outcome_probs(batter.by_group[g], pitcher.by_group[g], env.by_group[g]))


def signature_group(ace: arsenal.ArsenalPitcher, env: arsenal.ArsenalEnv) -> str:
    avg_batter, avg_pitcher = arsenal.average_batter(env), arsenal.average_pitcher(env)
    candidates = [g for g in GROUPS if ace.usage[g] >= SIGNATURE_MIN_USAGE]
    return min(candidates, key=lambda g: group_woba(avg_batter, ace, env, g) - group_woba(avg_batter, avg_pitcher, env, g))


def _probs_vector(batter, pitcher, env) -> np.ndarray:
    p = arsenal.outcome_probs(batter, pitcher, env)
    return np.array([p[o] for o in OUTCOMES])


def lineup_runs(vectors: list[np.ndarray]) -> dict:
    """Expected runs for a 9-man lineup's probability vectors vs. one pitcher, TIMES_THROUGH times through.

    per_batter folds each hitter's plate appearances back together.
    """
    table = np.array([vectors * TIMES_THROUGH])  # one "staff" member, 27 plate appearances
    result = runs.expected_runs_from_table(table)
    per_batter = result["per_batter"].reshape(TIMES_THROUGH, len(vectors)).sum(axis=0)
    return {"total": result["total"], "per_batter": per_batter, "table": table}


def build() -> dict:
    env = arsenal.league_environment({
        g: rows[list(COUNT_COLUMNS)].sum().to_dict()
        for g, rows in pd.read_csv(statcast.PITCHERS_FILE).groupby("group")
    })
    pitchers = _players(pd.read_csv(statcast.PITCHERS_FILE), ACE_MIN_BF)
    hitters = _players(pd.read_csv(statcast.BATTERS_FILE), HITTER_MIN_PA)
    hitter_models = {pid: arsenal.fit_batter(h["groups"], env) for pid, h in hitters.items()}

    avg_batter = arsenal.average_batter(env)
    fitted = {pid: arsenal.fit_pitcher(p["groups"], env) for pid, p in pitchers.items()}
    woba_allowed = {pid: arsenal.woba(arsenal.outcome_probs(avg_batter, m, env)) for pid, m in fitted.items()}
    ace_ids = sorted(fitted, key=woba_allowed.get)[:ACES]

    avg_pitcher = arsenal.average_pitcher(env)
    rng = random.Random(f"{par.PAR_SEED}:aces")
    hitter_ids = sorted(hitter_models)
    aces = []
    for pid in ace_ids:
        model = fitted[pid]
        vectors = {h: _probs_vector(hitter_models[h], model, env) for h in hitter_ids}
        scores = np.array([
            lineup_runs([vectors[h] for h in rng.sample(hitter_ids, LINEUP_SIZE)])["total"] for _ in range(par.PAR_SAMPLES)
        ])
        aces.append({
            "id": pid,
            "name": pitchers[pid]["name"],
            "years": pitchers[pid]["years"],
            "BF": pitchers[pid]["PA"],
            "wobaAllowed": woba_allowed[pid],
            "signature": signature_group(model, env),
            "groups": {
                g: {
                    "usage": model.usage[g],
                    "whiffRate": _whiff_rate(pitchers[pid]["groups"].get(g)),
                    "woba": group_woba(avg_batter, model, env, g),
                    "leagueWoba": group_woba(avg_batter, avg_pitcher, env, g),
                }
                for g in GROUPS
            },
            "model": arsenal.pitcher_to_json(model),
            **par.calibrate(scores, lower_is_better=False),
        })

    stored = {
        "environment": arsenal.env_to_json(env),
        "aces": aces,
        "hitters": {
            pid: {
                "name": h["name"],
                "years": h["years"],
                "PA": h["PA"],
                "groups": {g: {"PA": c["PA"], "swings": c["swings"], "whiffs": c["whiffs"]} for g, c in h["groups"].items()},
                "model": arsenal.batter_to_json(hitter_models[pid]),
            }
            for pid, h in hitters.items()
        },
    }
    CHALLENGE_FILE.write_text(json.dumps(stored, indent=1))
    return stored


class AceChallenge:
    kind = "lineup"

    def __init__(self):
        stored = json.loads(CHALLENGE_FILE.read_text())
        self.env = arsenal.env_from_json(stored["environment"])
        self.aces = stored["aces"]
        self.hitters = stored["hitters"]
        self.models = {pid: arsenal.batter_from_json(h["model"]) for pid, h in self.hitters.items()}
        self.avg_batter = arsenal.average_batter(self.env)
        self.avg_pitcher = arsenal.average_pitcher(self.env)

    def day(self, date: datetime.date) -> tuple[dict, list[str]]:
        """Today's ace and draft pool, the same for everyone on this UTC date."""
        rng = random.Random(f"aces:{date.isoformat()}")
        ace = self.aces[rng.randrange(len(self.aces))]
        return ace, rng.sample(sorted(self.hitters), POOL_SIZE)

    def _ace_model(self, ace: dict) -> arsenal.ArsenalPitcher:
        return arsenal.pitcher_from_json(ace["model"])

    def _neutral(self, pid: str, g: str) -> arsenal.ArsenalBatter:
        """The hitter with his rates vs. group g replaced by what his overall skill alone predicts."""
        b = self.models[pid]
        return arsenal.ArsenalBatter(b.overall, {**b.by_group, g: arsenal.group_prior(b.overall, self.env, g)})

    # ---------- JSON for the UI ----------

    def _ace_card(self, ace: dict) -> dict:
        sig = ace["signature"]
        return {
            "id": ace["id"],
            "name": ace["name"],
            "years": ace["years"],
            "BF": ace["BF"],
            "wobaAllowed": round(ace["wobaAllowed"], 3),
            "leagueWoba": round(arsenal.woba(arsenal.outcome_probs(self.avg_batter, self.avg_pitcher, self.env)), 3),
            "signature": sig,
            "signatureName": GROUP_NAMES[sig],
            "arsenal": [
                {
                    "group": g,
                    "name": GROUP_NAMES[g],
                    "usage": round(ace["groups"][g]["usage"], 3),
                    "whiffRate": ace["groups"][g]["whiffRate"],
                    "woba": round(ace["groups"][g]["woba"], 3),
                    "leagueWoba": round(ace["groups"][g]["leagueWoba"], 3),
                }
                for g in GROUPS
            ],
        }

    def _hitter_card(self, pid: str, sig: str) -> dict:
        h, b = self.hitters[pid], self.models[pid]
        seen = h["groups"].get(sig)
        return {
            "id": pid,
            "name": h["name"],
            "years": h["years"],
            "PA": h["PA"],
            "K": round(b.overall.rates["K"], 4),
            "woba": round(arsenal.woba(arsenal.outcome_probs(b, self.avg_pitcher, self.env)), 3),
            "sigWoba": round(group_woba(b, self.avg_pitcher, self.env, sig), 3),
            "sigExpected": round(group_woba(self._neutral(pid, sig), self.avg_pitcher, self.env, sig), 3),
            "sigPA": seen["PA"] if seen else 0,
            "sigWhiffRate": _whiff_rate(seen),
        }

    def challenge(self, date: datetime.date) -> dict:
        ace, pool = self.day(date)
        model = self._ace_model(ace)
        average = lineup_runs([_probs_vector(self.avg_batter, model, self.env)] * LINEUP_SIZE)["total"]
        sig = ace["signature"]
        return {
            "kind": self.kind,
            "themeKey": "aces",
            "date": date.isoformat(),
            "theme": THEME_LABEL,
            "headline": f"One ace. His {GROUP_NAMES[sig]}. Your nine.",
            "lever": sig,
            "leverName": f"handling his {GROUP_NAMES[sig]}",
            "pickCount": LINEUP_SIZE,
            "paPerPick": TIMES_THROUGH,
            "par": round(ace["par"], 2),
            "average": round(average, 2),
            "leagueSigWoba": round(ace["groups"][sig]["leagueWoba"], 3),
            "ace": self._ace_card(ace),
            "pool": [self._hitter_card(pid, sig) for pid in pool],
        }

    def simulate(self, date: datetime.date, picks: list[str]) -> dict:
        ace, pool = self.day(date)
        if len(picks) != LINEUP_SIZE or len(set(picks)) != LINEUP_SIZE or not set(picks) <= set(pool):
            raise ValueError(f"Pick {LINEUP_SIZE} different hitters from today's pool")

        env, sig = self.env, ace["signature"]
        model = self._ace_model(ace)
        vs = lambda batters, pitcher: lineup_runs([_probs_vector(b, pitcher, env) for b in batters])

        lineup = [self.models[p] for p in picks]
        neutral = [self._neutral(p, sig) for p in picks]
        average_lineup = [self.avg_batter] * LINEUP_SIZE

        yours = vs(lineup, model)
        baseline = vs(average_lineup, model)["total"]
        you_vs_average = vs(lineup, self.avg_pitcher)
        average_vs_average = vs(average_lineup, self.avg_pitcher)["total"]

        raw_quality = you_vs_average["total"] - average_vs_average
        matchup_edge = (yours["total"] - baseline) - raw_quality
        # Approximate share of the edge from the signature pitch: rerun with every
        # hitter's rates vs. that group set to what his overall skill predicts.
        lever_edge = (yours["total"] - vs(neutral, model)["total"]) - (
            you_vs_average["total"] - vs(neutral, self.avg_pitcher)["total"]
        )

        events = runs.sample_game_from_table(yours["table"], seed=f"{date.isoformat()}:{','.join(picks)}")
        for e in events:  # one row per time through the order
            e["pitcher"], e["batter"] = divmod(e["batter"], LINEUP_SIZE)

        return {
            "kind": self.kind,
            "date": date.isoformat(),
            "score": yours["total"],
            "par": ace["par"],
            "vsPar": yours["total"] - ace["par"],
            # Share of random lineups from the hitter pool that scored fewer runs than yours.
            "betterThanPct": par.percentile_rank(yours["total"], ace["percentiles"]),
            "average": baseline,
            "averageVsAverage": average_vs_average,
            "youVsAverage": you_vs_average["total"],
            "rawQuality": raw_quality,
            "matchupEdge": matchup_edge,
            "lever": sig,
            "leverName": f"handling his {GROUP_NAMES[sig]}",
            "leverEdge": lever_edge,
            "ace": self._ace_card(ace),
            "hitters": [
                {
                    **self._hitter_card(pid, sig),
                    "runs": float(yours["per_batter"][i]),
                    "runsVsAverage": float(you_vs_average["per_batter"][i]),
                    "wobaVsAce": round(arsenal.woba(arsenal.outcome_probs(self.models[pid], model, env)), 3),
                }
                for i, pid in enumerate(picks)
            ],
            "sampleRows": [f"{n} time through" for n in ("1st", "2nd", "3rd")][:TIMES_THROUGH],
            "sampleBatters": [self.hitters[pid]["name"] for pid in picks],
            "sampleGame": events,
        }


if __name__ == "__main__":
    stored = build()
    print(f"{len(stored['hitters'])} hitters with {HITTER_MIN_PA}+ PA in the pool")
    for ace in stored["aces"]:
        sig = ace["signature"]
        g = ace["groups"][sig]
        print(f"{ace['name']} ({ace['years']}, {ace['BF']} BF): wOBA allowed {ace['wobaAllowed']:.3f}, "
              f"signature {GROUP_NAMES[sig]} ({g['usage']:.0%} of PA, wOBA {g['woba']:.3f} vs lg {g['leagueWoba']:.3f}) | "
              f"par {ace['par']:.2f} runs, random lineups mean {ace['mean']:.2f}, sd {ace['std']:.2f}")
    print(f"Stored in {CHALLENGE_FILE}")
