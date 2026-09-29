"""
Daily Mode: a themed matchup puzzle scored against par.

Themes rotate by UTC date (THEME_ROTATION), so everyone plays the same puzzle:

  power    Power Hitters    draft 3 starters vs. nine career sluggers   lever: HR suppression
  aces     Great Pitchers   draft 9 hitters vs. one modern ace          lever: his signature pitch (aces.py)

This module holds the pitcher-draft themes (STAFF_THEMES). They share one
engine and differ only in how their Legends are chosen and which lever they
highlight, so a new one is a StaffTheme entry plus a candidates function.
Each UTC date picks one of the theme's precomputed Legends lineups and a pool
of elite career starters. The player drafts STAFF_SIZE pitchers; each faces
the lineup once through (9 PA each, 27 total). Every plate appearance is a
log5 matchup of era-adjusted career rates (matchup.py), and runs come from
the base-out engine (runs.py). The ranked score is expected runs allowed,
compared with the lineup's par. It never depends on the sampled reveal game.

Par is calibrated empirically (python -m warball.daily; see par.py):
thousands of random staffs from the elite pool face each lineup.
"""

import datetime
import json
import random
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from warball import aces, careers, data, par, runs
from warball.data import PROCESSED_DIR
from warball.matchup import BUCKETS, HIT_TYPES, Batter, Environment, Pitcher, average_batter, average_pitcher

THEME_ROTATION = ("power", "aces")

# Career floors: the lowest values where no short career reaches the top of
# the power or elite-starter leaderboards (3000 PA is ~5 full seasons).
LEGEND_MIN_CAREER_PA = 3000
STARTER_MIN_CAREER_BF = 3000

# A Legend must have played most of his career in the modern game (from
# careers.MODERN_GAME_START, when the pitching distance reached 60'6").
LEGEND_MIN_MODERN_SHARE = 0.5

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


def to_batter(row) -> Batter:
    babip = row["babip"] if "babip" in row and pd.notna(row["babip"]) else None
    return Batter(
        {b: float(row[b]) for b in BUCKETS},
        {t: float(row[f"mix_{t}"]) for t in HIT_TYPES},
        None if babip is None else float(babip),
    )


def to_pitcher(row) -> Pitcher:
    return Pitcher({b: float(row[b]) for b in BUCKETS})


def load_careers() -> tuple[pd.DataFrame, pd.DataFrame]:
    batters = pd.read_csv(careers.BATTERS_FILE).set_index("playerID")
    pitchers = pd.read_csv(careers.PITCHERS_FILE).set_index("playerID")
    return batters, pitchers


def legend_eligible(batters: pd.DataFrame) -> pd.DataFrame:
    """Careers long enough, and modern enough, to be any theme's Legend."""
    if "PA_modern" not in batters:
        raise KeyError("Career PA_modern missing: rerun python -m warball.pipeline")
    return batters[
        (batters["PA"] >= LEGEND_MIN_CAREER_PA) & (batters["PA_modern"] / batters["PA"] > LEGEND_MIN_MODERN_SHARE)
    ]


def power_candidates(batters: pd.DataFrame, env: Environment) -> pd.DataFrame:
    eligible = legend_eligible(batters)
    eligible = eligible[eligible["HR_total"] / eligible["PA"] >= POWER_MIN_RAW_HR_RATE]
    return eligible.nlargest(LEGEND_CANDIDATES, "HR")


@dataclass(frozen=True)
class StaffTheme:
    """A pitcher-draft theme: who the Legends are, and which bucket is the counter-lever."""
    key: str
    label: str
    headline: str
    blurb: str  # the end of the hero sentence: what drafting well means today
    lever: str  # the BUCKET the theme is built around
    lever_name: str
    candidates: Callable[[pd.DataFrame, Environment], pd.DataFrame]

    @property
    def lineups_file(self):
        return PROCESSED_DIR / f"daily_{self.key}.json"


STAFF_THEMES = {
    "power": StaffTheme(
        key="power",
        label="POWER HITTERS",
        headline="Nine career sluggers. Three arms. Beat par.",
        blurb="so keep the ball in the park and beat par.",
        lever="HR",
        lever_name="home-run suppression",
        candidates=power_candidates,
    ),
}


def deal_lineups(candidates: pd.DataFrame) -> list[list[str]]:
    """Snake-deal the ranked candidates so every lineup gets a similar mix of top and lower Legends."""
    if len(candidates) < LINEUPS * LINEUP_SIZE:
        raise ValueError(f"Only {len(candidates)} Legend candidates; {LINEUPS * LINEUP_SIZE} are needed")
    lineups = [[] for _ in range(LINEUPS)]
    for i, player in enumerate(candidates.index[: LINEUPS * LINEUP_SIZE]):
        rnd, pos = divmod(i, LINEUPS)
        lineups[pos if rnd % 2 == 0 else LINEUPS - 1 - pos].append(player)
    return lineups


def elite_starters(pitchers: pd.DataFrame) -> pd.DataFrame:
    return pitchers[
        (pitchers["role"] == "SP")
        & (pitchers["BF"] >= STARTER_MIN_CAREER_BF)
        & (pitchers["FIPminus"] <= ELITE_MAX_FIP_MINUS)
    ].sort_values("FIPminus")


def build_theme(theme: StaffTheme, batters: pd.DataFrame, pitchers: pd.DataFrame, env: Environment) -> dict:
    """Deal the theme's lineups, calibrate each one's par, and store them with the environment they assume."""
    elite_ids = list(elite_starters(pitchers).index)
    elite = [to_pitcher(pitchers.loc[p]) for p in elite_ids]
    rng = random.Random(f"{par.PAR_SEED}:{theme.key}")
    lineups = []
    for i, players in enumerate(deal_lineups(theme.candidates(batters, env))):
        lineup = [to_batter(batters.loc[p]) for p in players]
        scores = np.array([
            runs.expected_runs(lineup, rng.sample(elite, STAFF_SIZE), env)["total"] for _ in range(par.PAR_SAMPLES)
        ])
        lineups.append({"id": i, "players": players, **par.calibrate(scores)})
    stored = {
        "theme": theme.key,
        "environment": {"rates": env.rates, "babip": env.babip, "hit_mix": env.hit_mix},
        "elite_pool": elite_ids,
        "lineups": lineups,
    }
    theme.lineups_file.write_text(json.dumps(stored, indent=1))
    return stored


def build() -> dict:
    batters, pitchers = load_careers()
    env = careers.reference_environment(data.load_teams())
    return {key: build_theme(theme, batters, pitchers, env) for key, theme in STAFF_THEMES.items()}


class StaffChallenge:
    """One pitcher-draft theme's daily puzzle (e.g. Power Hitters)."""

    kind = "staff"

    def __init__(self, theme: StaffTheme, batters: pd.DataFrame, pitchers: pd.DataFrame):
        stored = json.loads(theme.lineups_file.read_text())
        self.theme = theme
        self.env = Environment(**stored["environment"])
        self.lineups = stored["lineups"]
        self.elite_pool = stored["elite_pool"]
        self.batters, self.pitchers = batters, pitchers

    def day(self, date: datetime.date) -> tuple[dict, list[str]]:
        """Today's lineup and draft pool, the same for everyone on this UTC date."""
        rng = random.Random(f"{self.theme.key}:{date.isoformat()}")
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
            "kind": self.kind,
            "themeKey": self.theme.key,
            "date": date.isoformat(),
            "theme": self.theme.label,
            "headline": self.theme.headline,
            "blurb": self.theme.blurb,
            "lever": self.theme.lever,
            "leverName": self.theme.lever_name,
            "pickCount": STAFF_SIZE,
            "paPerPick": LINEUP_SIZE,
            "par": round(lineup["par"], 2),
            "average": round(average_staff, 2),
            "reference": {b: round(v, 4) for b, v in self.env.rates.items() if b != "BIP"},
            "legends": [self._legend_card(p) for p in lineup["players"]],
            "pool": [self._pitcher_card(p) for p in pool],
        }

    def _lever_neutral(self, p: Pitcher) -> Pitcher:
        """The pitcher with his lever-bucket rate set to league average, the difference spread over his other buckets."""
        lever = self.theme.lever
        rates = dict(p.rates)
        spare = rates[lever] - self.env.rates[lever]
        rates[lever] = self.env.rates[lever]
        others = [b for b in BUCKETS if b != lever]
        total = sum(rates[b] for b in others)
        for b in others:
            rates[b] += spare * rates[b] / total
        return Pitcher(rates)

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

        # Approximate share of the edge from the theme's lever: rerun with each
        # pitcher's lever rate set to league average, against both lineups.
        neutral = [self._lever_neutral(p) for p in staff]
        lever_edge = (runs.expected_runs(legends, neutral, env)["total"] - yours["total"]) - (
            runs.expected_runs(avg_lineup, neutral, env)["total"] - vs_average_lineup["total"]
        )

        table = runs.matchup_table(legends, staff, env)
        avg_table = runs.matchup_table(legends, avg_staff, env)
        lever = runs.OUTCOMES.index(self.theme.lever)

        events = runs.sample_game_from_table(table, seed=f"{date.isoformat()}:{','.join(staff_ids)}")
        return {
            "kind": self.kind,
            "date": date.isoformat(),
            "score": yours["total"],
            "par": lineup_info["par"],
            "vsPar": yours["total"] - lineup_info["par"],
            # Share of random elite staffs that allowed more runs than you.
            "betterThanPct": 100 - par.percentile_rank(yours["total"], lineup_info["percentiles"]),
            "average": baseline,
            "averageVsAverage": average_vs_average,
            "averageVsYou": vs_average_lineup["total"],
            "rawQuality": raw_quality,
            "matchupEdge": matchup_edge,
            "lever": self.theme.lever,
            "leverName": self.theme.lever_name,
            "leverEdge": lever_edge,
            "staff": [
                {
                    **self._pitcher_card(pid),
                    "runsAllowed": float(yours["per_pitcher"][i]),
                    "runsVsAverageLineup": float(vs_average_lineup["per_pitcher"][i]),
                    "lever": float(table[i, :, lever].sum()),
                }
                for i, pid in enumerate(staff_ids)
            ],
            "legends": [
                {
                    "name": self.batters.loc[pid, "name"],
                    "lever": float(table[:, j, lever].sum()),
                    "leverVsAverage": float(avg_table[:, j, lever].sum()),
                    "runs": float(yours["per_batter"][j]),
                }
                for j, pid in enumerate(lineup_info["players"])
            ],
            "sampleRows": [self.pitchers.loc[pid, "name"] for pid in staff_ids],
            "sampleBatters": [self.batters.loc[pid, "name"] for pid in lineup_info["players"]],
            "sampleGame": events,
        }


class DailyChallenge:
    """Every built theme, rotated by UTC date. Themes whose data isn't built yet are skipped."""

    def __init__(self):
        self.themes = {}
        built = [t for t in STAFF_THEMES.values() if t.lineups_file.exists()]
        if built:
            batters, pitchers = load_careers()
            self.themes |= {t.key: StaffChallenge(t, batters, pitchers) for t in built}
        if aces.CHALLENGE_FILE.exists():
            self.themes["aces"] = aces.AceChallenge()
        if not self.themes:
            raise FileNotFoundError(
                "No Daily Mode themes are built: run python -m warball.daily (and python -m warball.aces for Theme C)"
            )

    def theme_key(self, date: datetime.date) -> str:
        available = [k for k in THEME_ROTATION if k in self.themes]
        return available[date.toordinal() % len(available)]

    def _theme(self, date: datetime.date, key: str | None):
        key = key or self.theme_key(date)
        if key not in self.themes:
            raise ValueError(f"Theme {key!r} isn't built (built: {', '.join(self.themes)})")
        return self.themes[key]

    def challenge(self, date: datetime.date, theme: str | None = None) -> dict:
        return self._theme(date, theme).challenge(date)

    def simulate(self, date: datetime.date, picks: list[str], theme: str | None = None) -> dict:
        return self._theme(date, theme).simulate(date, picks)


if __name__ == "__main__":
    built = build()
    for key, stored in built.items():
        print(f"\n{STAFF_THEMES[key].label}")
        for lineup in stored["lineups"]:
            print(f"Lineup {lineup['id']}: par {lineup['par']:.2f} | random elite staffs: mean {lineup['mean']:.2f}, "
                  f"sd {lineup['std']:.2f}, best {lineup['best']:.2f}, worst {lineup['worst']:.2f}")
        print(f"Stored {len(stored['lineups'])} lineups and a {len(stored['elite_pool'])}-pitcher elite pool "
              f"in {STAFF_THEMES[key].lineups_file}")
