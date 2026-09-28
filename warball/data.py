"""Loaders for the local Lahman CSVs (see scripts/phase0_test_lahman_pull.py for setup)."""

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "lahman"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def load_table(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        print(f"Missing {path}. Download the Lahman database and place its CSVs under {DATA_DIR}.")
        sys.exit(1)
    df = pd.read_csv(path, low_memory=False)

    # 1871-1875 (the National Association, pre-dating the modern NL) has a
    # blank lgID in every Lahman table. Left as NaN, that drops the whole era
    # out of every yearID+lgID groupby/merge in league.py, silently turning
    # those player-seasons' WAR/FIP/OPS+/ERA+ into NaN instead of computing
    # them against their own (small, early) league. Give it a real label
    # instead so those five seasons get judged against each other.
    if "lgID" in df.columns:
        df["lgID"] = df["lgID"].fillna("NA")

    return df


def load_batting() -> pd.DataFrame:
    return load_table("Batting")


def load_pitching() -> pd.DataFrame:
    return load_table("Pitching")


def load_fielding() -> pd.DataFrame:
    return load_table("Fielding")


def load_teams() -> pd.DataFrame:
    return load_table("Teams")


def load_people() -> pd.DataFrame:
    return load_table("People")


def load_fielding_of() -> pd.DataFrame:
    return load_table("FieldingOF")


def load_fielding_of_split() -> pd.DataFrame:
    return load_table("FieldingOFsplit")


def load_managers() -> pd.DataFrame:
    return load_table("Managers")
