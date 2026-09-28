"""
Phase 0 validation — Baseball Savant Statcast test pull for Theme C.

This is the riskiest technical assumption in the whole project: that
pitch-type-level performance data (e.g. wOBA against a specific pitch
type) is actually pullable via pybaseball. Kershaw is the test case
because his signature pitch (curveball) is public knowledge, so the
result is sanity-checkable against something real.

Usage:
    pip install -r requirements.txt
    python scripts/phase0_test_statcast_pull.py
"""

import pandas as pd
from pybaseball import playerid_lookup, statcast_pitcher

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)

SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "hit_into_play",
}
WHIFF_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked"}


def get_kershaw_id() -> int:
    lookup = playerid_lookup("kershaw", "clayton")
    if lookup.empty:
        raise RuntimeError("playerid_lookup returned no match for Kershaw — check pybaseball/Chadwick register access")
    return int(lookup.iloc[0]["key_mlbam"])


def pull_sample(pitcher_id: int, start: str, end: str) -> pd.DataFrame:
    df = statcast_pitcher(start, end, pitcher_id)
    if df.empty:
        raise RuntimeError(f"No Statcast pitches returned for pitcher {pitcher_id} in {start}..{end}")
    return df


def summarize_by_pitch_type(df: pd.DataFrame) -> pd.DataFrame:
    needed = {"pitch_type", "pitch_name", "description", "woba_value", "woba_denom"}
    missing = needed - set(df.columns)
    assert not missing, f"Missing Statcast columns: {missing}"

    df = df.dropna(subset=["pitch_type"]).copy()
    df["is_swing"] = df["description"].isin(SWING_DESCRIPTIONS)
    df["is_whiff"] = df["description"].isin(WHIFF_DESCRIPTIONS)

    grouped = df.groupby("pitch_type")
    summary = pd.DataFrame({
        "pitch_name": grouped["pitch_name"].first(),
        "n_pitches": grouped.size(),
        "usage_rate": (grouped.size() / len(df)).round(3),
        "whiff_rate": (grouped["is_whiff"].sum() / grouped["is_swing"].sum()).round(3),
        "woba_against": (grouped["woba_value"].sum() / grouped["woba_denom"].sum()).round(3),
    })
    return summary.sort_values("n_pitches", ascending=False)


if __name__ == "__main__":
    pid = get_kershaw_id()
    print(f"Kershaw MLBAM ID: {pid}")

    df = pull_sample(pid, "2022-04-01", "2022-10-01")
    print(f"Pulled {len(df)} pitches from the 2022 season")

    summary = summarize_by_pitch_type(df)
    print("\nPer-pitch-type breakdown:")
    print(summary)

    most_used = summary["n_pitches"].idxmax()
    best_whiff = summary["whiff_rate"].idxmax()
    best_woba = summary["woba_against"].idxmin()

    print(f"\nMost-thrown pitch: {most_used} ({summary.loc[most_used, 'pitch_name']})")
    print(f"Best whiff rate:   {best_whiff} ({summary.loc[best_whiff, 'pitch_name']})")
    print(f"Lowest wOBA against: {best_woba} ({summary.loc[best_woba, 'pitch_name']})")

    is_curveball = lambda code: code in ("CU", "KC")
    if is_curveball(best_whiff) or is_curveball(best_woba):
        print(
            "\nSanity check PASSED: curveball shows up as Kershaw's most effective "
            "pitch (highest whiff rate and/or lowest wOBA against), matching public "
            "scouting-report knowledge, even though it isn't necessarily his most-thrown pitch."
        )
    else:
        print(
            "\nSanity check FAILED expectations: curveball isn't standing out as Kershaw's "
            "best pitch by whiff rate or wOBA against. Before building Theme C on this data, "
            "check the date range, sample size, and whether 'CU' is the right pitch_type code "
            "for this season (Statcast pitch classifications have shifted over time)."
        )
