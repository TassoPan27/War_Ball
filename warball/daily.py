"""
Daily Mode: a pitcher-only matchup puzzle scored against par.

Each UTC date picks one of the theme's precomputed Legends lineups and a pool
of elite career starters. The player drafts STAFF_SIZE pitchers; each faces
the lineup once through (9 PA each, 27 total). Every plate appearance is a
log5 matchup of era-adjusted career rates (matchup.py), and runs come from
the base-out engine (runs.py). The ranked score is expected runs allowed,
compared with the lineup's par. It never depends on the sampled reveal game.

Par is calibrated empirically (python -m warball.daily): thousands of random
staffs from the elite pool face each lineup, and par sits at PAR_PERCENTILE
of that distribution. If balance feels off, move par, not the Legends.
"""

import datetime
import json
import random

import numpy as np
import pandas as pd

from warball import careers, data, runs
from warball.data import PROCESSED_DIR
from warball.matchup import BUCKETS, HIT_TYPES, Batter, Environment, Pitcher, average_batter, average_pitcher

THEME = "power"
THEME_LABEL = "POWER HITTERS"

# Career floors: the lowest values where no short career reaches the top of
# the power or elite-starter leaderboards (3000 PA is ~5 full seasons).
LEGEND_MIN_CAREER_PA = 3000
STARTER_MIN_CAREER_BF = 3000

# A power Legend must also have hit home runs in his own time. Odds-ratio era
# adjustment turns dominance of a near-zero dead-ball league HR rate into an
# implausible modern one (Home Run Baker, 96 career HR, would rank 8th ever).
POWER_MIN_RAW_HR_RATE = 0.04
LEGEND_CANDIDATES = 45
LINEUPS = 5
LINEUP_SIZE = 9

ELITE_MAX_FIP_MINUS = 80  # elite = career FIP- at least 20% better than league
POOL_SIZE = 12
STAFF_SIZE = 3

PAR_PERCENTILE = 70  # of staff quality: roughly 30% of random staffs beat par
PAR_SAMPLE_STAFFS = 3000
PAR_SEED = "warball-par-calibration"

LINEUPS_FILE = PROCESSED_DIR / "daily_lineups.json"


def to_batter(row) -> Batter:
    return Batter({b: float(row[b]) for b in BUCKETS}, {t: float(row[f"mix_{t}"]) for t in HIT_TYPES})


def to_pitcher(row) -> Pitcher:
    return Pitcher({b: float(row[b]) for b in BUCKETS})


def load_careers() -> tuple[pd.DataFrame, pd.DataFrame]:
    batters = pd.read_csv(careers.BATTERS_FILE).set_index("playerID")
    pitchers = pd.read_csv(careers.PITCHERS_FILE).set_index("playerID")
    return batters, pitchers


def power_candidates(batters: pd.DataFrame) -> pd.DataFrame:
    eligible = batters[
        (batters["PA"] >= LEGEND_MIN_CAREER_PA) & (batters["HR_total"] / batters["PA"] >= POWER_MIN_RAW_HR_RATE)
    ]
    return eligible.nlargest(LEGEND_CANDIDATES, "HR")


def deal_lineups(candidates: pd.DataFrame) -> list[list[str]]:
    """Snake-deal the ranked candidates so every lineup gets a similar mix of top and lower sluggers."""
    lineups = [[] for _ in range(LINEUPS)]
    for i, player in enumerate(candidates.index):
        rnd, pos = divmod(i, LINEUPS)
        lineups[pos if rnd % 2 == 0 else LINEUPS - 1 - pos].append(player)
    return lineups


def elite_starters(pitchers: pd.DataFrame) -> pd.DataFrame:
    return pitchers[
        (pitchers["role"] == "SP")
        & (pitchers["BF"] >= STARTER_MIN_CAREER_BF)
        & (pitchers["FIPminus"] <= ELITE_MAX_FIP_MINUS)
    ].sort_values("FIPminus")


def calibrate_par(lineup: list[Batter], elite: list[Pitcher], env: Environment, rng: random.Random) -> dict:
    scores = np.array([
        runs.expected_runs(lineup, rng.sample(elite, STAFF_SIZE), env)["total"] for _ in range(PAR_SAMPLE_STAFFS)
    ])
    return {
        "par": float(np.percentile(scores, 100 - PAR_PERCENTILE)),
        "mean": float(scores.mean()),
        "std": float(scores.std()),
        "best": float(scores.min()),
        "worst": float(scores.max()),
        # Runs-allowed value at each percentile 0-100, for "better than N% of staffs".
        "percentiles": [float(v) for v in np.percentile(scores, np.arange(101))],
    }


def build() -> dict:
    """Deal the theme's lineups, calibrate each one's par, and store them with the environment they assume."""
    batters, pitchers = load_careers()
    env = careers.reference_environment(data.load_teams())
    elite = [to_pitcher(r) for _, r in elite_starters(pitchers).iterrows()]
    rng = random.Random(PAR_SEED)
    lineups = []
    for i, players in enumerate(deal_lineups(power_candidates(batters))):
        lineup = [to_batter(batters.loc[p]) for p in players]
        lineups.append({"id": i, "players": players, **calibrate_par(lineup, elite, env, rng)})
    stored = {
        "theme": THEME,
        "environment": {"rates": env.rates, "babip": env.babip, "hit_mix": env.hit_mix},
        "elite_pool": list(elite_starters(pitchers).index),
        "lineups": lineups,
    }
    LINEUPS_FILE.write_text(json.dumps(stored, indent=1))
    return stored


class DailyChallenge:
    def __init__(self):
        if not LINEUPS_FILE.exists():
            raise FileNotFoundError(f"{LINEUPS_FILE} is missing: run python -m warball.daily to calibrate par")
        stored = json.loads(LINEUPS_FILE.read_text())
        self.env = Environment(**stored["environment"])
        self.lineups = stored["lineups"]
        self.elite_pool = stored["elite_pool"]
        self.batters, self.pitchers = load_careers()

    def day(self, date: datetime.date) -> tuple[dict, list[str]]:
        """Today's lineup and draft pool, the same for everyone on this UTC date."""
        rng = random.Random(f"{THEME}:{date.isoformat()}")
        lineup = self.lineups[rng.randrange(len(self.lineups))]
        return lineup, rng.sample(self.elite_pool, POOL_SIZE)

    # ---------- JSON for the UI ----------

    def _rates(self, row) -> dict:
        return {b: round(float(row[b]), 4) for b in ("K", "BB", "HR")}

    def _legend_card(self, player: str) -> dict:
        r = self.batters.loc[player]
        return {
            "id": player,
            "name": r["name"],
            "years": f"{int(r['first_year'])}-{int(r['last_year'])}",
            "PA": int(r["PA"]),
            "HR": int(r["HR_total"]),
            "rawHrRate": round(float(r["HR_total"] / r["PA"]), 4),
            "ISO": round(float(r["ISO"]), 3),
            "adjusted": self._rates(r),
        }

    def _pitcher_card(self, player: str) -> dict:
        r = self.pitchers.loc[player]
        return {
            "id": player,
            "name": r["name"],
            "years": f"{int(r['first_year'])}-{int(r['last_year'])}",
            "IP": round(float(r["IP"])),
            "FIP": round(float(r["FIP"]), 2),
            "FIPminus": round(float(r["FIPminus"])),
            "HR9": round(float(r["HR_total"] * 9 / r["IP"]), 2),
            "adjusted": self._rates(r),
        }

    def challenge(self, date: datetime.date) -> dict:
        lineup, pool = self.day(date)
        legends = [to_batter(self.batters.loc[p]) for p in lineup["players"]]
        average_staff = runs.expected_runs(legends, [average_pitcher(self.env)] * STAFF_SIZE, self.env)["total"]
        return {
            "date": date.isoformat(),
            "theme": THEME_LABEL,
            "staffSize": STAFF_SIZE,
            "paPerArm": LINEUP_SIZE,
            "par": round(lineup["par"], 2),
            "averageStaff": round(average_staff, 2),
            "reference": {b: round(v, 4) for b, v in self.env.rates.items() if b != "BIP"},
            "legends": [self._legend_card(p) for p in lineup["players"]],
            "pool": [self._pitcher_card(p) for p in pool],
        }

    def simulate(self, date: datetime.date, staff_ids: list[str]) -> dict:
        lineup_info, pool = self.day(date)
        if len(staff_ids) != STAFF_SIZE or len(set(staff_ids)) != STAFF_SIZE or not set(staff_ids) <= set(pool):
            raise ValueError(f"Pick {STAFF_SIZE} different pitchers from today's pool")

        env = self.env
        legends = [to_batter(self.batters.loc[p]) for p in lineup_info["players"]]
        staff = [to_pitcher(self.pitchers.loc[p]) for p in staff_ids]
        avg_lineup = [average_batter(env)] * LINEUP_SIZE
        avg_staff = [average_pitcher(env)] * STAFF_SIZE

        yours = runs.expected_runs(legends, staff, env)
        baseline = runs.expected_runs(legends, avg_staff, env)["total"]
        vs_average_lineup = runs.expected_runs(avg_lineup, staff, env)
        average_vs_average = runs.expected_runs(avg_lineup, avg_staff, env)["total"]

        raw_quality = average_vs_average - vs_average_lineup["total"]
        matchup_edge = (baseline - yours["total"]) - raw_quality

        # Approximate share of the edge from home-run suppression: rerun with each
        # pitcher's HR rate set to league average (the difference spread over his other buckets).
        def hr_neutral(p: Pitcher) -> Pitcher:
            rates = dict(p.rates)
            spare = rates["HR"] - env.rates["HR"]
            rates["HR"] = env.rates["HR"]
            others = [b for b in BUCKETS if b != "HR"]
            total = sum(rates[b] for b in others)
            for b in others:
                rates[b] += spare * rates[b] / total
            return Pitcher(rates)

        neutral = [hr_neutral(p) for p in staff]
        hr_edge = (runs.expected_runs(legends, neutral, env)["total"] - yours["total"]) - (
            runs.expected_runs(avg_lineup, neutral, env)["total"] - vs_average_lineup["total"]
        )

        table = runs.matchup_table(legends, staff, env)
        avg_table = runs.matchup_table(legends, avg_staff, env)
        hr = runs.OUTCOMES.index("HR")
        percentile = float(np.interp(yours["total"], lineup_info["percentiles"], np.arange(101)))

        events = runs.sample_game(legends, staff, env, seed=f"{date.isoformat()}:{','.join(staff_ids)}")
        return {
            "date": date.isoformat(),
            "score": yours["total"],
            "par": lineup_info["par"],
            "vsPar": yours["total"] - lineup_info["par"],
            "betterThanPct": 100 - percentile,  # share of random elite staffs you allowed fewer runs than
            "averageStaff": baseline,
            "averageLineupVsAverageStaff": average_vs_average,
            "averageLineupVsYou": vs_average_lineup["total"],
            "rawQuality": raw_quality,
            "matchupEdge": matchup_edge,
            "hrEdge": hr_edge,
            "staff": [
                {
                    **self._pitcher_card(pid),
                    "runsAllowed": float(yours["per_pitcher"][i]),
                    "runsVsAverageLineup": float(vs_average_lineup["per_pitcher"][i]),
                    "homeRuns": float(table[i, :, hr].sum()),
                }
                for i, pid in enumerate(staff_ids)
            ],
            "legends": [
                {
                    "name": self.batters.loc[pid, "name"],
                    "homeRuns": float(table[:, j, hr].sum()),
                    "homeRunsVsAverage": float(avg_table[:, j, hr].sum()),
                    "runs": float(yours["per_batter"][j]),
                }
                for j, pid in enumerate(lineup_info["players"])
            ],
            "sampleGame": events,
        }


if __name__ == "__main__":
    stored = build()
    for lineup in stored["lineups"]:
        print(f"Lineup {lineup['id']}: par {lineup['par']:.2f} | random elite staffs: mean {lineup['mean']:.2f}, "
              f"sd {lineup['std']:.2f}, best {lineup['best']:.2f}, worst {lineup['worst']:.2f}")
    print(f"Stored {len(stored['lineups'])} lineups and a {len(stored['elite_pool'])}-pitcher elite pool in {LINEUPS_FILE}")
