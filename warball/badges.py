"""
Specialization badges for Classic Mode cards (docs: player-badges-spec.md).

A badge is a label on a real, already-computed stat clearing a threshold,
never an invented composite. For each draftable player-season:

  - The stat is a season rate from the stat pipeline, shrunk toward that
    year+league's average (SHRINK_PA / SHRINK_BF), so a short season can't
    ride an extreme small-sample rate.
  - The threshold is a percentile within the same year+league pool of
    draft-qualified seasons (the draft's PA/IP floors apply before any badge
    is considered): top BADGE_PERCENTILE, or bottom for "less is better" stats.
  - "Sustained" badges (Iron Man, Workhorse) also need the player to reach
    that level in at least SUSTAINED_MIN_SEASONS seasons of his career.
  - A badge the data can't support for a season (strikeouts or caught
    stealing not recorded; no batted-ball data at all) is reported as
    unavailable with a reason, never approximated.

Every badge is worth the same BADGE_RUNS in the season sim for now (see
season.py); badge tiers can scale that later.
"""

import math

import numpy as np
import pandas as pd

BADGE_PERCENTILE = 0.10  # top (or bottom) 10% of the year+league pool
BADGE_RUNS = 3.0  # season-sim runs per badge (scored for hitters, saved for pitchers)
BADGE_MIN_POOL = 10  # fewer qualified seasons than this in a year+league: no percentile badges
SUSTAINED_MIN_SEASONS = 3
SB_MIN_ATTEMPTS = 20  # Base Thief: no small-sample 3-for-3 base stealers
RELIEVER_GS_SHARE = 0.5  # Bullpen Weapon pool: under half of his games were starts
ERA_PLUS_CAP = 400.0  # a 0.00 ERA has no ERA+; treat it as this before shrinking

# Shrinkage: plate appearances (at-bats for ISO) or batters faced of league-average
# performance added to each season's rate, matching careers.py where the stat overlaps.
SHRINK_PA = {"ISO": 250, "BB": 150, "K": 100, "2B": 250, "SB": 200, "SB_SUCCESS": 20}
SHRINK_BF = {"K": 150, "BB": 250, "HR": 600}
SHRINK_RELIEF_IP = 30

POOL_KEYS = ["yearID", "lgID"]

HITTER_BADGES = {
    "slugger": "Slugger",
    "table_setter": "Table-Setter",
    "bat_to_ball": "Bat-to-Ball",
    "gap_power": "Gap Power",
    "base_thief": "Base Thief",
    "iron_man": "Iron Man",
}
PITCHER_BADGES = {
    "strikeout_artist": "Strikeout Artist",
    "control_specialist": "Control Specialist",
    "homer_suppressor": "Homer Suppressor",
    "workhorse": "Workhorse",
    "bullpen_weapon": "Bullpen Weapon",
}
GROUNDBALL_UNAVAILABLE = {
    "name": "Groundball Machine",
    "reason": "No batted-ball data in this project's sources (it would need 2002+ tracking data).",
}


def _shrunk(count: pd.Series, n: pd.Series, df: pd.DataFrame, k: float) -> pd.Series:
    """count/n shrunk toward the year+league pool's rate by k pseudo-trials."""
    pool_rate = count.groupby([df[c] for c in POOL_KEYS]).transform("sum") / n.groupby([df[c] for c in POOL_KEYS]).transform("sum")
    return (count + pool_rate * k) / (n + k)


def _percentile(value: pd.Series, df: pd.DataFrame, higher_is_better: bool, min_pool: int = BADGE_MIN_POOL) -> pd.Series:
    """Percentile (0-1, 1 = best) within the year+league pool; ties share the better rank. NaN = not in the pool."""
    ranked = value if higher_is_better else -value
    pct = ranked.groupby([df[c] for c in POOL_KEYS]).rank(pct=True, method="max")
    pool_size = ranked.notna().groupby([df[c] for c in POOL_KEYS]).transform("sum")
    return pct.where(pool_size >= min_pool)


def _earned(pct: pd.Series) -> pd.Series:
    return pct.fillna(0) > 1 - BADGE_PERCENTILE


def _top(pct: float) -> str:
    return f"top {max(1, math.ceil((1 - pct) * 100))}%"


def _sustained(earned: pd.Series, df: pd.DataFrame) -> pd.Series:
    """Earned this season, and in at least SUSTAINED_MIN_SEASONS seasons of the player's career."""
    seasons = df.loc[earned, ["playerID", "yearID"]].drop_duplicates().groupby("playerID").size()
    return earned & df["playerID"].map(seasons).fillna(0).ge(SUSTAINED_MIN_SEASONS)


def _collect(df: pd.DataFrame, awards: list, unavailable: list) -> pd.DataFrame:
    """awards: (key, name, earned mask, pct, detail fn(row) -> str); unavailable: (name, mask, reason)."""
    out = df.copy()
    badges = [[] for _ in range(len(df))]
    missing = [[] for _ in range(len(df))]
    for key, name, earned, pct, detail in awards:
        for i in np.flatnonzero(earned.to_numpy()):
            row = df.iloc[i]
            badges[i].append({"key": key, "name": name, "detail": f"{detail(row)} · {_top(pct.iloc[i])} of {int(row['yearID'])} {row['lgID']}"})
    for name, mask, reason in unavailable:
        for i in np.flatnonzero(mask.to_numpy()):
            missing[i].append({"name": name, "reason": reason})
    out["badges"] = badges
    out["badges_unavailable"] = missing
    return out


def hitter_badges(seasons: pd.DataFrame) -> pd.DataFrame:
    """Adds `badges` and `badges_unavailable` to draft-qualified hitter seasons (batting_stats + teamG)."""
    df = seasons.reset_index(drop=True)
    pa, ab = df["PA"], df["AB"].where(df["AB"] > 0)
    so_recorded = ~df["SO_missing"].astype(bool)
    cs_recorded = ~df["CS_missing"].astype(bool)

    iso = _shrunk(df["2B"] + 2 * df["3B"] + 3 * df["HR"], ab, df, SHRINK_PA["ISO"])
    bb = _shrunk(df["BB"] + df["HBP"], pa, df, SHRINK_PA["BB"])
    k = _shrunk(df["SO"].where(so_recorded), pa.where(so_recorded), df, SHRINK_PA["K"])
    doubles = _shrunk(df["2B"], pa, df, SHRINK_PA["2B"])

    attempts = df["SB"] + df["CS"]
    sb_rate = _shrunk(df["SB"].where(cs_recorded), pa.where(cs_recorded), df, SHRINK_PA["SB"])
    attempted = cs_recorded & (attempts >= SB_MIN_ATTEMPTS)
    success = _shrunk(df["SB"].where(attempted), attempts.where(attempted), df, SHRINK_PA["SB_SUCCESS"])

    games_share = df["G"] / df["teamG"]

    pct = {
        "slugger": _percentile(iso, df, True),
        "table_setter": _percentile(bb, df, True),
        "bat_to_ball": _percentile(k, df, False),
        "gap_power": _percentile(doubles, df, True),
        "sb_rate": _percentile(sb_rate, df, True),
        # Ranked only among that year's real base stealers (SB_MIN_ATTEMPTS+), which
        # can be a handful of players; the pool-size rule already binds on sb_rate.
        "sb_success": _percentile(success, df, True, min_pool=1),
        "iron_man": _percentile(games_share, df, True),
    }
    base_thief = _earned(pct["sb_rate"]) & _earned(pct["sb_success"])
    iron_man = _sustained(_earned(pct["iron_man"]), df)

    awards = [
        ("slugger", HITTER_BADGES["slugger"], _earned(pct["slugger"]), pct["slugger"],
         lambda r: f"ISO {(r['2B'] + 2 * r['3B'] + 3 * r['HR']) / r['AB']:.3f}"),
        ("table_setter", HITTER_BADGES["table_setter"], _earned(pct["table_setter"]), pct["table_setter"],
         lambda r: f"BB% {(r['BB'] + r['HBP']) / r['PA']:.1%}"),
        ("bat_to_ball", HITTER_BADGES["bat_to_ball"], _earned(pct["bat_to_ball"]), pct["bat_to_ball"],
         lambda r: f"K% {r['SO'] / r['PA']:.1%}"),
        ("gap_power", HITTER_BADGES["gap_power"], _earned(pct["gap_power"]), pct["gap_power"],
         lambda r: f"{int(r['2B'])} 2B ({r['2B'] / r['PA'] * 600:.0f} per 600 PA)"),
        ("base_thief", HITTER_BADGES["base_thief"], base_thief, pct["sb_rate"],
         lambda r: f"{int(r['SB'])} SB, {r['SB'] / (r['SB'] + r['CS']):.0%} success"),
        ("iron_man", HITTER_BADGES["iron_man"], iron_man, pct["iron_man"],
         lambda r: f"{int(r['G'])} of {int(r['teamG'])} G"),
    ]
    unavailable = [
        (HITTER_BADGES["bat_to_ball"], ~so_recorded, "Strikeouts weren't recorded for this season."),
        (HITTER_BADGES["base_thief"], ~cs_recorded, "Caught stealing wasn't recorded for this season."),
    ]
    return _collect(df, awards, unavailable)


def pitcher_badges(seasons: pd.DataFrame) -> pd.DataFrame:
    """Adds `badges` and `badges_unavailable` to draft-qualified pitcher seasons (pitching_stats + teamG + slots)."""
    df = seasons.reset_index(drop=True)
    # A few early seasons have no batters-faced count; estimate it like careers.py does.
    bf = df["BFP"].where(df["BFP"] > 0, df["IP"] * 3 + df["H"] + df["BB"] + df["HBP"])

    k = _shrunk(df["SO"], bf, df, SHRINK_BF["K"])
    bb = _shrunk(df["BB"] + df["HBP"], bf, df, SHRINK_BF["BB"])
    hr = _shrunk(df["HR"], bf, df, SHRINK_BF["HR"])
    ip_share = df["IP"] / df["teamG"]

    reliever = (df["GS"] < RELIEVER_GS_SHARE * df["G"]) & df["slots"].map(lambda s: "RP" in s)
    era_plus = df["ERAplus"].fillna(ERA_PLUS_CAP).clip(upper=ERA_PLUS_CAP).where(reliever)
    era_plus = (era_plus * df["IP"] + 100 * SHRINK_RELIEF_IP) / (df["IP"] + SHRINK_RELIEF_IP)

    pct = {
        "strikeout_artist": _percentile(k, df, True),
        "control_specialist": _percentile(bb, df, False),
        "homer_suppressor": _percentile(hr, df, False),
        "workhorse": _percentile(ip_share, df, True),
        "bullpen_weapon": _percentile(era_plus, df, True),
    }
    workhorse = _sustained(_earned(pct["workhorse"]), df)

    awards = [
        ("strikeout_artist", PITCHER_BADGES["strikeout_artist"], _earned(pct["strikeout_artist"]), pct["strikeout_artist"],
         lambda r: f"K% {r['SO'] / _bf(r):.1%}"),
        ("control_specialist", PITCHER_BADGES["control_specialist"], _earned(pct["control_specialist"]), pct["control_specialist"],
         lambda r: f"BB% {(r['BB'] + r['HBP']) / _bf(r):.1%}"),
        ("homer_suppressor", PITCHER_BADGES["homer_suppressor"], _earned(pct["homer_suppressor"]), pct["homer_suppressor"],
         lambda r: f"HR/9 {r['HR'] * 9 / r['IP']:.2f}"),
        ("workhorse", PITCHER_BADGES["workhorse"], workhorse, pct["workhorse"],
         lambda r: f"{r['IP']:.0f} IP"),
        ("bullpen_weapon", PITCHER_BADGES["bullpen_weapon"], _earned(pct["bullpen_weapon"]), pct["bullpen_weapon"],
         lambda r: f"ERA+ {min(r['ERAplus'], ERA_PLUS_CAP) if pd.notna(r['ERAplus']) else ERA_PLUS_CAP:.0f} (relievers)"),
    ]
    unavailable = [(GROUNDBALL_UNAVAILABLE["name"], pd.Series(True, index=df.index), GROUNDBALL_UNAVAILABLE["reason"])]
    return _collect(df, awards, unavailable)


def _bf(row) -> float:
    return row["BFP"] if row["BFP"] > 0 else row["IP"] * 3 + row["H"] + row["BB"] + row["HBP"]
