"""
Classic Mode draft pool, Era Ball style: every pick spins a random franchise
and decade, and you draft one player off that roster.

Each player on a spun roster is a single card: their peak season *with that
franchise, in that decade*. 2020s Cubs Kris Bryant is his 2021 (Cubs stint
only), not his 2016 MVP year. Peak = the most valuable qualifying season:
highest WAR for hitters, most FIP-based runs saved for pitchers (volume-aware,
so a full season of ace work beats a short relief stint with a better rate).

After the roster is full, one more spin drafts a coach: a real manager of
that franchise in that decade (see qualified_managers).
"""

import random
from typing import NamedTuple

import pandas as pd

from warball import data
from warball.badges import hitter_badges, pitcher_badges
from warball.constants import PYTHAGOREAN_EXPONENT, SEASON_GAMES
from warball.eligibility import (
    BATTER_MIN_PA,
    BATTER_PA_PER_TEAM_GAME,
    SEASON_KEYS,
    batter_positions,
    center_fielders,
    hitter_slots,
    pitcher_slots,
)
from warball.data import PROCESSED_DIR

# A franchise needs this many seasons in a decade to go on the wheel: keeps
# all 30 current franchises plus long-running Negro League and 19th-century
# clubs, and drops one-year teams too thin to draft a roster from.
MIN_SEASONS_IN_DECADE = 3

PEAK_KEYS = ["franchID", "decade", "playerID"]


class Spin(NamedTuple):
    franchID: str
    decade: int
    label: str
    team_name: str


def _team_info(teams: pd.DataFrame) -> pd.DataFrame:
    info = teams[["yearID", "teamID", "franchID", "name", "G"]].rename(
        columns={"name": "team_name", "G": "teamG"}
    )
    info["decade"] = info["yearID"] // 10 * 10
    return info


def _with_names(df: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    names = people[["playerID", "nameFirst", "nameLast"]].copy()
    names["name"] = (names["nameFirst"].fillna("") + " " + names["nameLast"].fillna("")).str.strip()
    names = names.rename(columns={"nameLast": "last"})
    merged = df.merge(names[["playerID", "name", "last"]], on="playerID", how="left")
    merged["name"] = merged["name"].fillna(merged["playerID"])
    merged["last"] = merged["last"].fillna(merged["name"])
    return merged


def _peak(seasons: pd.DataFrame, value_col: str) -> pd.DataFrame:
    return seasons.sort_values(value_col, ascending=False).drop_duplicates(PEAK_KEYS)


def qualified_hitter_seasons(
    batting: pd.DataFrame, fielding: pd.DataFrame, cf: pd.DataFrame, info: pd.DataFrame
) -> pd.DataFrame:
    df = batting.merge(info, on=["yearID", "teamID"])
    df = df[(df["PA"] >= BATTER_PA_PER_TEAM_GAME * df["teamG"]) & (df["PA"] >= BATTER_MIN_PA)]
    positions = batter_positions(fielding, info[["yearID", "teamID", "teamG"]])
    df = df.merge(positions, on=SEASON_KEYS, how="left").merge(cf, on=SEASON_KEYS, how="left")
    df["slots"] = [hitter_slots(p) for p in df["positions"]]
    df["cf"] = df["cf"].eq(True)
    return df.drop(columns="positions")


def qualified_pitcher_seasons(pitching: pd.DataFrame, info: pd.DataFrame) -> pd.DataFrame:
    df = pitching.merge(info, on=["yearID", "teamID"])
    df["slots"] = [pitcher_slots(*vals) for vals in zip(df["G"], df["GS"], df["IP"], df["teamG"])]
    return df[df["slots"].map(bool)]


def qualified_managers(managers: pd.DataFrame, teams: pd.DataFrame, info: pd.DataFrame) -> pd.DataFrame:
    """One card per manager per franchise-decade: wins above what his teams' runs predicted.

    Expected wins come from the Pythagorean formula applied to each team-season's
    actual runs scored/allowed, prorated to the games he managed. Unlike a
    player's single peak season, a manager is judged on his whole stint with
    that club in that decade: one season's gap between actual and Pythagorean
    wins is mostly luck. Needs at least a full season's worth of games.
    """
    df = managers.merge(teams[["yearID", "teamID", "R", "RA"]], on=["yearID", "teamID"])
    df = df.merge(info, on=["yearID", "teamID"]).dropna(subset=["R", "RA"])
    rs = df["R"] ** PYTHAGOREAN_EXPONENT
    ra = df["RA"] ** PYTHAGOREAN_EXPONENT
    df["expected_W"] = rs / (rs + ra) * (df["W"] + df["L"])

    cards = df.groupby(PEAK_KEYS, as_index=False).agg(
        G=("G", "sum"),
        W=("W", "sum"),
        L=("L", "sum"),
        expected_W=("expected_W", "sum"),
        first_year=("yearID", "min"),
        last_year=("yearID", "max"),
    )
    cards["wins_vs_pythag"] = (cards["W"] - cards["expected_W"]) / (cards["W"] + cards["L"]) * SEASON_GAMES

    full_season = info.groupby(["franchID", "decade"], as_index=False)["teamG"].max()
    cards = cards.merge(full_season, on=["franchID", "decade"])
    return cards[cards["G"] >= cards["teamG"]].drop(columns="teamG")


def _spin_wheel(info: pd.DataFrame) -> pd.DataFrame:
    wheel = (
        info.groupby(["franchID", "decade"])
        .agg(seasons=("yearID", "nunique"), team_name=("team_name", lambda s: s.mode().iat[0]))
        .reset_index()
    )
    wheel = wheel[wheel["seasons"] >= MIN_SEASONS_IN_DECADE].reset_index(drop=True)
    wheel["label"] = wheel["decade"].astype(str) + "s " + wheel["team_name"]
    return wheel


class DraftPool:
    def __init__(self):
        teams = data.load_teams()
        people = data.load_people()
        info = _team_info(teams)

        batting = pd.read_csv(PROCESSED_DIR / "batting_stats.csv")
        pitching = pd.read_csv(PROCESSED_DIR / "pitching_stats.csv")
        cf = center_fielders(data.load_fielding_of(), data.load_fielding_of_split(), data.load_batting())

        # Badges are percentiles within each year+league's qualified seasons, so
        # they're computed on every qualified season before picking peaks.
        hitter_seasons = hitter_badges(qualified_hitter_seasons(batting, data.load_fielding(), cf, info))
        self.hitter_seasons = _with_names(hitter_seasons, people)
        self.pitcher_seasons = _with_names(pitcher_badges(qualified_pitcher_seasons(pitching, info)), people)
        self.hitters = _peak(self.hitter_seasons, "WAR")
        self.pitchers = _peak(self.pitcher_seasons, "runs_saved")
        self.managers = _with_names(qualified_managers(data.load_managers(), teams, info), people)
        self.wheel = _spin_wheel(info)

    def spin(self, rng: random.Random) -> Spin:
        row = self.wheel.iloc[rng.randrange(len(self.wheel))]
        return Spin(row["franchID"], int(row["decade"]), row["label"], row["team_name"])

    def _on_spin(self, cards: pd.DataFrame, spin: Spin) -> pd.Series:
        return (cards["franchID"] == spin.franchID) & (cards["decade"] == spin.decade)

    def roster_for(self, spin: Spin, exclude_player_ids=()) -> tuple[pd.DataFrame, pd.DataFrame]:
        """The spun team-decade's (hitter, pitcher) cards, best first, minus anyone already drafted."""

        def available(cards: pd.DataFrame, value_col: str) -> pd.DataFrame:
            mask = self._on_spin(cards, spin) & ~cards["playerID"].isin(list(exclude_player_ids))
            return cards[mask].sort_values(value_col, ascending=False)

        return available(self.hitters, "WAR"), available(self.pitchers, "runs_saved")

    def managers_for(self, spin: Spin) -> pd.DataFrame:
        return self.managers[self._on_spin(self.managers, spin)].sort_values("wins_vs_pythag", ascending=False)
