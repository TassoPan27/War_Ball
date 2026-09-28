"""
Per year+league context: league-average rates that every player-season is
compared against. This is the actual era-adjustment mechanism — a player's
raw stats are always measured relative to *their own* year+league's average,
not to a fixed modern baseline, so a .300 OBP in 1968 and a .340 OBP in 1999
can both come out to a roughly average rating if that's what they were.
"""

import pandas as pd

from warball.constants import WOBA_WEIGHTS


def _team_batting_totals(teams: pd.DataFrame) -> pd.DataFrame:
    df = teams[["yearID", "lgID", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SF"]].copy()
    for col in ("HBP", "SF"):
        df[col] = df[col].fillna(0)
    return df.groupby(["yearID", "lgID"], as_index=False).sum(numeric_only=True)


def _team_pitching_totals(teams: pd.DataFrame) -> pd.DataFrame:
    df = teams[["yearID", "lgID", "ER", "ERA", "IPouts", "HRA", "BBA", "SOA", "HBP"]].copy()
    df["HBP"] = df["HBP"].fillna(0)
    grouped = df.groupby(["yearID", "lgID"], as_index=False).agg(
        ER=("ER", "sum"),
        IPouts=("IPouts", "sum"),
        HRA=("HRA", "sum"),
        BBA=("BBA", "sum"),
        SOA=("SOA", "sum"),
        HBP=("HBP", "sum"),
    )
    grouped["IP"] = grouped["IPouts"] / 3.0
    # Recompute league ERA from earned runs / IP rather than averaging each
    # team's ERA, so it's innings-weighted instead of team-weighted.
    grouped["ERA"] = grouped["ER"] / grouped["IP"] * 9
    return grouped


def batting_context(teams: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per (yearID, lgID) with lgOBP, lgSLG, lgwOBA."""
    totals = _team_batting_totals(teams)

    totals["1B"] = totals["H"] - totals["2B"] - totals["3B"] - totals["HR"]
    totals["TB"] = totals["1B"] + 2 * totals["2B"] + 3 * totals["3B"] + 4 * totals["HR"]
    totals["PA"] = totals["AB"] + totals["BB"] + totals["HBP"] + totals["SF"]

    totals["lgOBP"] = (totals["H"] + totals["BB"] + totals["HBP"]) / totals["PA"]
    totals["lgSLG"] = totals["TB"] / totals["AB"]

    w = WOBA_WEIGHTS
    woba_num = (
        w["uBB"] * totals["BB"]
        + w["HBP"] * totals["HBP"]
        + w["1B"] * totals["1B"]
        + w["2B"] * totals["2B"]
        + w["3B"] * totals["3B"]
        + w["HR"] * totals["HR"]
    )
    totals["lgwOBA"] = woba_num / totals["PA"]

    return totals[["yearID", "lgID", "lgOBP", "lgSLG", "lgwOBA"]]


def matchup_context(teams: pd.DataFrame) -> pd.DataFrame:
    """Per (yearID, lgID) per-PA rates for the batter-vs-pitcher matchup model (see matchup.py).

    Batting-side rates describe the league a hitter played in; pitching-side
    rates (HR/BB/SO *allowed*) describe the league a pitcher faced. League PA
    stands in for league batters faced, since the two are the same plate
    appearances seen from each side.
    """
    cols = ["yearID", "lgID", "AB", "H", "2B", "3B", "HR", "BB", "SO", "HBP", "SF", "R", "HRA", "BBA", "SOA", "IPouts"]
    df = teams[cols].copy()
    for col in ("SO", "HBP", "SF"):
        df[col] = df[col].fillna(0)
    t = df.groupby(["yearID", "lgID"], as_index=False).sum(numeric_only=True)

    pa = t["AB"] + t["BB"] + t["HBP"] + t["SF"]
    singles = t["H"] - t["2B"] - t["3B"] - t["HR"]
    balls_in_play = pa - t["HR"] - t["BB"] - t["HBP"] - t["SO"]
    w = WOBA_WEIGHTS
    return pd.DataFrame({
        "yearID": t["yearID"],
        "lgID": t["lgID"],
        "bat_HR": t["HR"] / pa,
        "bat_BB": (t["BB"] + t["HBP"]) / pa,
        "bat_SO": t["SO"] / pa,
        "bat_BIP_value": (w["1B"] * singles + w["2B"] * t["2B"] + w["3B"] * t["3B"]) / balls_in_play,
        "R_per_PA": t["R"] / pa,
        "pit_HR": t["HRA"] / pa,
        "pit_BB": (t["BBA"] + t["HBP"]) / pa,
        "pit_SO": t["SOA"] / pa,
        "pit_HR9": t["HRA"] * 27 / t["IPouts"],
    })


def pitching_context(teams: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per (yearID, lgID) with lgERA and the FIP constant."""
    totals = _team_pitching_totals(teams)

    fip_raw = (13 * totals["HRA"] + 3 * (totals["BBA"] + totals["HBP"]) - 2 * totals["SOA"]) / totals["IP"]
    totals["fip_constant"] = totals["ERA"] - fip_raw

    return totals[["yearID", "lgID", "ERA", "fip_constant"]].rename(columns={"ERA": "lgERA"})
