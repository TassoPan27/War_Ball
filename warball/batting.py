"""
Per player-team-season batting stats: wOBA, OPS+, and approximate batting WAR.

The grain is one row per player per team per season, so a mid-season trade
yields two rows — each judged on only what that player did for that team,
in that team's park.
"""

import pandas as pd

from warball.constants import (
    PA_NORM,
    POSITIONAL_ADJUSTMENT_PER_600PA,
    REPLACEMENT_RUNS_PER_600PA,
    RUNS_PER_WIN,
    WOBA_SCALE,
    WOBA_WEIGHTS,
)
from warball.eligibility import SEASON_KEYS
from warball.league import batting_context


def _aggregate_seasons(batting: pd.DataFrame) -> pd.DataFrame:
    """Merges the rare multiple stints with the same team in one season."""
    df = batting.copy()
    for col in ("IBB", "HBP", "SF", "SO"):
        df[col] = df[col].fillna(0)

    return df.groupby(SEASON_KEYS, as_index=False).agg(
        lgID=("lgID", "first"),
        G=("G", "sum"),
        AB=("AB", "sum"),
        H=("H", "sum"),
        b2B=("2B", "sum"),
        b3B=("3B", "sum"),
        HR=("HR", "sum"),
        BB=("BB", "sum"),
        IBB=("IBB", "sum"),
        SO=("SO", "sum"),
        HBP=("HBP", "sum"),
        SF=("SF", "sum"),
    )


def _primary_position(fielding: pd.DataFrame) -> pd.DataFrame:
    """Picks each player-team-season's most-played position, for the positional adjustment."""
    grouped = fielding.groupby(SEASON_KEYS + ["POS"], as_index=False)["G"].sum()
    primary = grouped.sort_values("G", ascending=False).drop_duplicates(SEASON_KEYS)
    return primary[SEASON_KEYS + ["POS"]]


def compute_batting_stats(batting: pd.DataFrame, fielding: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    seasons = _aggregate_seasons(batting)
    seasons = seasons[seasons["AB"] > 0].copy()

    seasons["1B"] = seasons["H"] - seasons["b2B"] - seasons["b3B"] - seasons["HR"]
    seasons["TB"] = seasons["1B"] + 2 * seasons["b2B"] + 3 * seasons["b3B"] + 4 * seasons["HR"]
    seasons["PA"] = seasons["AB"] + seasons["BB"] + seasons["HBP"] + seasons["SF"]
    seasons["uBB"] = seasons["BB"] - seasons["IBB"]

    seasons["OBP"] = (seasons["H"] + seasons["BB"] + seasons["HBP"]) / seasons["PA"]
    seasons["SLG"] = seasons["TB"] / seasons["AB"]

    w = WOBA_WEIGHTS
    woba_num = (
        w["uBB"] * seasons["uBB"]
        + w["HBP"] * seasons["HBP"]
        + w["1B"] * seasons["1B"]
        + w["2B"] * seasons["b2B"]
        + w["3B"] * seasons["b3B"]
        + w["HR"] * seasons["HR"]
    )
    seasons["wOBA"] = woba_num / seasons["PA"]

    ctx = batting_context(teams)
    seasons = seasons.merge(ctx, on=["yearID", "lgID"], how="left")
    seasons = seasons.merge(teams[["yearID", "teamID", "BPF"]], on=["yearID", "teamID"], how="left")
    seasons["BPF"] = seasons["BPF"].fillna(100)

    seasons["OPS_plus"] = (
        100 * (seasons["OBP"] / seasons["lgOBP"] + seasons["SLG"] / seasons["lgSLG"] - 1)
    ) / (seasons["BPF"] / 100)
    seasons["wRAA"] = (seasons["wOBA"] - seasons["lgwOBA"]) / WOBA_SCALE * seasons["PA"]

    pos = _primary_position(fielding)
    seasons = seasons.merge(pos, on=SEASON_KEYS, how="left")
    # No fielding row at all for a team-season means they only hit: a DH.
    seasons["POS"] = seasons["POS"].fillna("DH")
    seasons["pos_adj_runs"] = (
        seasons["POS"].map(POSITIONAL_ADJUSTMENT_PER_600PA).fillna(0) * (seasons["PA"] / PA_NORM)
    )

    seasons["replacement_runs"] = REPLACEMENT_RUNS_PER_600PA * (seasons["PA"] / PA_NORM)
    seasons["WAR"] = (
        seasons["wRAA"] + seasons["pos_adj_runs"] + seasons["replacement_runs"]
    ) / RUNS_PER_WIN

    return seasons[
        [
            "playerID", "yearID", "teamID", "lgID", "POS",
            "G", "PA", "AB", "H", "b2B", "b3B", "HR", "BB", "HBP", "SF", "SO",
            "OBP", "SLG", "wOBA", "OPS_plus", "wRAA", "pos_adj_runs",
            "replacement_runs", "WAR",
        ]
    ].rename(columns={"OPS_plus": "OPSplus", "b2B": "2B", "b3B": "3B"})
