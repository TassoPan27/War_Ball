"""
Phase 1 checklist — Core Stat Pipeline.

Runs the shared engine (warball/pipeline.py) and checks off each roadmap item:
  - wOBA + approximate WAR for batters
  - FIP for pitchers
  - era-adjusted (and, as a bonus, park-adjusted) OPS+/ERA+
  - the engine is "frozen" to data/processed/ CSVs both modes can read

Since there's no ground truth to assert against (this is an approximation,
not a bref replica), the check is a sanity comparison: run a small, era-spanning
batch of well-known players through the engine and eyeball whether the numbers
land in the neighborhood of their real, publicly-known career figures.

Usage:
    python -m warball.pipeline   # (re)build data/processed/*.csv if needed
    python scripts/phase1_check.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball.data import PROCESSED_DIR
from warball.pipeline import build

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)

# Real, publicly-known career figures (Baseball-Reference), for eyeballing —
# not asserted against, since our formulas are documented approximations.
KNOWN_BATTING = {
    "ruthba01": ("Babe Ruth", "WAR ~182.6, OPS+ 206"),
    "cobbty01": ("Ty Cobb", "WAR ~151.4, OPS+ 168"),
    "bondsba01": ("Barry Bonds", "WAR ~162.8 (incl. defense), OPS+ 182"),
}
KNOWN_PITCHING = {
    "kershcl01": ("Clayton Kershaw", "ERA+ ~157, FIP ~2.85"),
    "maddugr01": ("Greg Maddux", "ERA+ ~132, FIP ~3.26"),
}


def check_batting(batting_stats: pd.DataFrame):
    print("=== Batting: wOBA + approximate WAR ===")
    needed = {"wOBA", "wRAA", "pos_adj_runs", "replacement_runs", "WAR", "OPSplus"}
    missing = needed - set(batting_stats.columns)
    assert not missing, f"Missing batting engine columns: {missing}"
    assert batting_stats["wOBA"].between(0, 1).mean() > 0.99, "wOBA out of a sane 0-1 range too often"

    career = (
        batting_stats[batting_stats["playerID"].isin(KNOWN_BATTING)]
        .groupby("playerID")
        .agg(seasons=("yearID", "nunique"), career_WAR=("WAR", "sum"), avg_OPSplus=("OPSplus", "mean"))
    )
    career["known_bref_figures"] = career.index.map(lambda pid: KNOWN_BATTING[pid][1])
    career["name"] = career.index.map(lambda pid: KNOWN_BATTING[pid][0])
    print(career[["name", "seasons", "career_WAR", "avg_OPSplus", "known_bref_figures"]].round(1))


def check_pitching(pitching_stats: pd.DataFrame):
    print("\n=== Pitching: FIP + era/park-adjusted ERA+ ===")
    needed = {"FIP", "ERAplus", "ERA"}
    missing = needed - set(pitching_stats.columns)
    assert not missing, f"Missing pitching engine columns: {missing}"
    assert pitching_stats["FIP"].between(-5, 15).mean() > 0.95, "FIP out of a sane range too often"

    sample = pitching_stats[pitching_stats["playerID"].isin(KNOWN_PITCHING)].copy()
    sample["ERAplus_w"] = sample["ERAplus"] * sample["IP"]
    career = sample.groupby("playerID").agg(
        seasons=("yearID", "nunique"), IP=("IP", "sum"), avg_FIP=("FIP", "mean"), ERAplus_w=("ERAplus_w", "sum")
    )
    career["career_ERAplus"] = career["ERAplus_w"] / career["IP"]
    career["known_bref_figures"] = career.index.map(lambda pid: KNOWN_PITCHING[pid][1])
    career["name"] = career.index.map(lambda pid: KNOWN_PITCHING[pid][0])
    print(career[["name", "seasons", "IP", "avg_FIP", "career_ERAplus", "known_bref_figures"]].round(1))


def check_edge_cases(pitching_stats: pd.DataFrame):
    print("\n=== Edge case: 0.00 ERA in a tiny sample shouldn't blow up ERA+ ===")
    zero_era = pitching_stats[(pitching_stats["ERA"] == 0)]
    print(f"{len(zero_era)} player-seasons with a 0.00 ERA")
    bad = zero_era[zero_era["ERAplus"].apply(lambda x: x in (float("inf"), float("-inf")))]
    assert bad.empty, f"Found {len(bad)} infinite ERA+ values — divide-by-zero not handled"
    print("Confirmed: these come back as NaN (undefined), not inf.")


if __name__ == "__main__":
    batting_stats, pitching_stats = build()
    print(f"Froze {len(batting_stats)} batting and {len(pitching_stats)} pitching player-team-seasons to {PROCESSED_DIR}\n")

    check_batting(batting_stats)
    check_pitching(pitching_stats)
    check_edge_cases(pitching_stats)

    print("\nPhase 1 check passed: wOBA/WAR, FIP, and OPS+/ERA+ all compute, and the engine is frozen to disk.")
