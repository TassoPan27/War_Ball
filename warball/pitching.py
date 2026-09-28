"""
Per player-team-season pitching stats: FIP, park+era-adjusted ERA+, and
FIP-based runs saved. Same grain as batting.py: a mid-season trade yields one
row per team.
"""

import numpy as np
import pandas as pd

from warball.eligibility import SEASON_KEYS
from warball.league import pitching_context


def _aggregate_seasons(pitching: pd.DataFrame) -> pd.DataFrame:
    """Merges the rare multiple stints with the same team in one season."""
    df = pitching.copy()
    for col in ("HBP", "BFP"):
        df[col] = df[col].fillna(0)

    return df.groupby(SEASON_KEYS, as_index=False).agg(
        lgID=("lgID", "first"),
        G=("G", "sum"),
        GS=("GS", "sum"),
        IPouts=("IPouts", "sum"),
        H=("H", "sum"),
        ER=("ER", "sum"),
        HR=("HR", "sum"),
        BB=("BB", "sum"),
        SO=("SO", "sum"),
        HBP=("HBP", "sum"),
        BFP=("BFP", "sum"),
    )


def compute_pitching_stats(pitching: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    seasons = _aggregate_seasons(pitching)
    seasons = seasons[seasons["IPouts"] > 0].copy()
    seasons["IP"] = seasons["IPouts"] / 3.0

    ctx = pitching_context(teams)
    seasons = seasons.merge(ctx, on=["yearID", "lgID"], how="left")
    seasons = seasons.merge(teams[["yearID", "teamID", "PPF"]], on=["yearID", "teamID"], how="left")
    seasons["PPF"] = seasons["PPF"].fillna(100)

    seasons["FIP"] = (
        13 * seasons["HR"] + 3 * (seasons["BB"] + seasons["HBP"]) - 2 * seasons["SO"]
    ) / seasons["IP"] + seasons["fip_constant"]

    # FIP is calibrated so league FIP == league ERA, so this is runs saved vs.
    # a league-average pitcher over the same innings. Volume-aware, like WAR.
    seasons["runs_saved"] = (seasons["lgERA"] - seasons["FIP"]) * seasons["IP"] / 9
    # FIP-: FIP as a percent of league average (100 = average, lower is better).
    # Era-adjusted like ERA+, but not park-adjusted (FanGraphs' version is).
    seasons["FIPminus"] = 100 * seasons["FIP"] / seasons["lgERA"]

    seasons["ERA"] = seasons["ER"] / seasons["IP"] * 9
    # A 0.00 ERA (common in tiny position-player-pitching stints) would divide
    # by zero into +inf rather than a meaningful rating — leave it undefined.
    era_for_ratio = seasons["ERA"].replace(0, np.nan)
    # A pitcher's raw ERA is inflated by a hitter-friendly park (PPF > 100),
    # which deflates the raw lgERA/ERA ratio — multiplying by PPF/100 restores
    # the credit a park-neutral comparison owes them.
    seasons["ERA_plus"] = 100 * (seasons["lgERA"] / era_for_ratio) * (seasons["PPF"] / 100)
    # Note: unlike OPS+, an IP-weighted league average of ERA+ does not come
    # out to ~100 — it's a ratio of ratios (lgERA/ERA), and by Jensen's
    # inequality the weighted average of a reciprocal runs a bit hot (~108-110
    # here). That's an inherent property of this classic formula, not a bug;
    # real-world ERA+ has the same quirk.

    return seasons[
        [
            "playerID", "yearID", "teamID", "lgID", "G", "GS", "IP", "BFP",
            "H", "ER", "HR", "BB", "HBP", "SO", "ERA", "FIP", "FIPminus", "ERA_plus", "runs_saved",
        ]
    ].rename(columns={"ERA_plus": "ERAplus"})
