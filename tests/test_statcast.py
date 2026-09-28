"""The Statcast reduce/aggregate steps on a hand-built handful of pitches (no network)."""

import pandas as pd

from warball import statcast


def raw_pitches() -> pd.DataFrame:
    rows = [
        # batter, pitcher, pitch_type, description, events, game_type
        (1, 9, "CU", "swinging_strike", None, "R"),
        (1, 9, "KC", "swinging_strike", "strikeout", "R"),  # knuckle curve -> CU group
        (1, 9, "FF", "hit_into_play", "home_run", "R"),
        (1, 9, "ST", "ball", "walk", "R"),  # sweeper -> SL group
        (2, 9, "SI", "hit_into_play", "field_error", "R"),  # reached on error = out in play
        (2, 9, "CH", "foul", None, "R"),
        (2, 9, "CH", "hit_into_play", "sac_bunt", "R"),  # bunts are left out
        (2, 9, "KN", "hit_into_play", "single", "R"),  # knuckleball: no group, dropped
        (2, 9, "FF", "hit_into_play", "double", "S"),  # spring training: dropped
    ]
    df = pd.DataFrame(rows, columns=["batter", "pitcher", "pitch_type", "description", "events", "game_type"])
    df["game_year"] = 2019
    return df


def test_reduce_maps_groups_swings_and_outcomes():
    r = statcast.reduce(raw_pitches())
    assert list(r["group"]) == ["CU", "CU", "FB", "SL", "FB", "CH", "CH"]
    assert list(r["swing"]) == [1, 1, 1, 0, 1, 1, 1]
    assert list(r["whiff"]) == [1, 1, 0, 0, 0, 0, 0]
    assert list(r["outcome"].fillna("")) == ["", "K", "HR", "BB", "OUT", "", ""]


def test_counts_by_group():
    counts = statcast.counts_by_group(statcast.reduce(raw_pitches()), "batter").set_index(["player", "group"])
    assert counts.loc[(1, "CU"), "PA"] == 1 and counts.loc[(1, "CU"), "K"] == 1
    assert counts.loc[(1, "CU"), "swings"] == 2 and counts.loc[(1, "CU"), "whiffs"] == 2
    assert counts.loc[(1, "FB"), "HR"] == 1
    assert counts.loc[(2, "FB"), "OUT"] == 1
    assert counts.loc[(2, "CH"), "PA"] == 0 and counts.loc[(2, "CH"), "swings"] == 2  # seen, but no PA ended on one
    assert counts["first_year"].eq(2019).all()
