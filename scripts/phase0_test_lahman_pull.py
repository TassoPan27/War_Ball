"""
Phase 0 validation — Lahman database test pull.

Confirms that the batting/pitching/fielding fields WARBall needs (HR, K%, BB%,
innings, etc.) are present in the Lahman tables and checks how clean/complete
they are across eras, since Classic Mode and Daily Mode Themes A/B need this
to work for any season in baseball history, not just modern ones.

DATA SETUP (do this once):
    pybaseball's built-in Lahman fetcher points at chadwickbureau/baseballdatabank
    on GitHub, which is dead as of 2026-09-22 (repo 404s, no longer listed under
    the chadwickbureau org). Rather than trust an unverified third-party mirror,
    this script reads the CSVs from a local folder you populate yourself:

    1. Download the Lahman database from a source you trust, e.g.:
         - https://www.seanlahman.com/  (official site; check "Statistics" /
           download page — was unreachable from this environment when this
           script was written, may be back up for you)
         - https://www.kaggle.com/datasets/danielmontilla/baseball-databank
       Either the classic seanlahman.com distribution (flat CSVs) or the
       baseballdatabank "core" folder both work — this script looks in both
       layouts.
    2. Unzip it and place (or symlink) the CSVs so these three exist:
         data/lahman/Batting.csv
         data/lahman/Pitching.csv
         data/lahman/Fielding.csv
       (If your download nests them under a "core/" subfolder, just copy that
       core/ folder's contents straight into data/lahman/.)

Usage:
    pip install -r requirements.txt
    python scripts/phase0_test_lahman_pull.py
"""

import sys
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "lahman"

# A small, era-spanning batch: old-timers, steroid-era sluggers, a modern ace.
TEST_PLAYERS = {
    "ruthba01": "Babe Ruth",
    "cobbty01": "Ty Cobb",
    "bondsba01": "Barry Bonds",
    "maddugr01": "Greg Maddux",
    "kershcl01": "Clayton Kershaw",
}


def load_table(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        print(f"\nMissing {path}")
        print(
            "Download the Lahman database and place its CSVs under "
            f"{DATA_DIR} (see the setup instructions at the top of this script)."
        )
        sys.exit(1)
    return pd.read_csv(path, low_memory=False)


def check_batting() -> pd.DataFrame:
    print("=== Batting ===")
    batting = load_table("Batting")

    needed = {"playerID", "yearID", "AB", "H", "2B", "3B", "HR", "BB", "SO", "SF", "HBP"}
    missing = needed - set(batting.columns)
    assert not missing, f"Missing batting columns: {missing}"

    # SF and HBP weren't tracked league-wide in early baseball history — confirm
    # that shows up as NaNs rather than silently-wrong zeros, so downstream wOBA
    # math can handle it deliberately (fillna(0)) instead of by accident.
    null_pct = batting[["SF", "HBP", "SO", "BB"]].isna().mean().round(3)
    print(f"Null rate across full table (by column):\n{null_pct}\n")

    sample = batting[batting["playerID"].isin(TEST_PLAYERS)].copy()
    print(f"Rows pulled for test players: {len(sample)} (across all their seasons)")

    for col in ("SF", "HBP", "SO", "BB"):
        sample[col] = sample[col].fillna(0)

    career = sample.groupby("playerID").agg(
        seasons=("yearID", "nunique"),
        AB=("AB", "sum"),
        H=("H", "sum"),
        HR=("HR", "sum"),
        BB=("BB", "sum"),
        SO=("SO", "sum"),
        HBP=("HBP", "sum"),
        SF=("SF", "sum"),
    )
    career["PA"] = career["AB"] + career["BB"] + career["HBP"] + career["SF"]
    career["K_pct"] = (career["SO"] / career["PA"]).round(3)
    career["BB_pct"] = (career["BB"] / career["PA"]).round(3)
    career["name"] = career.index.map(TEST_PLAYERS)

    print(career[["name", "seasons", "PA", "HR", "K_pct", "BB_pct"]])
    return sample


def check_pitching() -> pd.DataFrame:
    print("\n=== Pitching ===")
    pitching = load_table("Pitching")

    needed = {"playerID", "yearID", "IPouts", "H", "ER", "HR", "BB", "SO", "BFP", "ERA"}
    missing = needed - set(pitching.columns)
    assert not missing, f"Missing pitching columns: {missing}"

    null_pct = pitching[["IPouts", "HR", "BB", "SO", "BFP"]].isna().mean().round(3)
    print(f"Null rate across full table (by column):\n{null_pct}\n")

    sample = pitching[pitching["playerID"].isin(TEST_PLAYERS)].copy()
    print(f"Rows pulled for test players: {len(sample)} (across all their seasons)")

    career = sample.groupby("playerID").agg(
        seasons=("yearID", "nunique"),
        IPouts=("IPouts", "sum"),
        HR=("HR", "sum"),
        BB=("BB", "sum"),
        SO=("SO", "sum"),
        BFP=("BFP", "sum"),
    )
    career["IP"] = (career["IPouts"] / 3).round(1)
    career["HR_per_9"] = (career["HR"] / career["IP"] * 9).round(2)
    career["BB_pct"] = (career["BB"] / career["BFP"]).round(3)
    career["name"] = career.index.map(TEST_PLAYERS)

    print(career[["name", "seasons", "IP", "HR_per_9", "BB_pct"]])
    return sample


def check_fielding() -> pd.DataFrame:
    print("\n=== Fielding ===")
    fielding = load_table("Fielding")

    needed = {"playerID", "yearID", "POS", "InnOuts", "PO", "A", "E"}
    missing = needed - set(fielding.columns)
    assert not missing, f"Missing fielding columns: {missing}"

    sample = fielding[fielding["playerID"].isin(TEST_PLAYERS)].copy()
    print(f"Rows pulled for test players: {len(sample)}")
    print(sample.groupby("playerID")["POS"].unique())
    return sample


if __name__ == "__main__":
    check_batting()
    check_pitching()
    check_fielding()
    print("\nPhase 0 Lahman check passed: needed columns present for all three tables.")

