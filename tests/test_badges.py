"""Badge rules (warball/badges.py) on synthetic draft-qualified seasons."""

import numpy as np
import pandas as pd

from warball import badges, season
from warball.roster import Roster
from warball.eligibility import ALL_SLOTS


def hitters(n=40, year=1990, lg="NL", seed=0):
    rng = np.random.default_rng(seed)
    pa = rng.integers(450, 700, n)
    df = pd.DataFrame({
        "playerID": [f"h{year}{lg}{i}" for i in range(n)], "yearID": year, "lgID": lg, "teamID": "T",
        "PA": pa, "AB": (pa * 0.9).astype(int), "2B": (pa * 0.04).astype(int), "3B": 3, "HR": (pa * 0.03).astype(int),
        "BB": (pa * 0.08).astype(int), "HBP": 3, "SO": (pa * 0.15).astype(int), "SB": 5, "CS": 3,
        "G": 140, "teamG": 162, "SO_missing": False, "CS_missing": False,
    })
    return df


def names(df, pid):
    return [b["name"] for b in df.loc[df["playerID"] == pid, "badges"].iloc[0]]


def test_percentile_badges_go_to_the_extremes_and_can_stack():
    df = hitters()
    df.loc[0, ["HR", "BB"]] = [55, 150]  # a Bonds season: slugger and table-setter
    df.loc[1, "SO"] = 10  # bat-to-ball
    out = badges.hitter_badges(df)
    assert {"Slugger", "Table-Setter"} <= set(names(out, df.loc[0, "playerID"]))
    assert "Bat-to-Ball" in names(out, df.loc[1, "playerID"])
    slugger = next(b for b in out.loc[0, "badges"] if b["key"] == "slugger")
    assert "ISO" in slugger["detail"] and "top" in slugger["detail"] and "1990 NL" in slugger["detail"]
    share = out["badges"].map(lambda bs: any(b["key"] == "slugger" for b in bs)).mean()
    assert share <= badges.BADGE_PERCENTILE + 0.03


def test_unrecorded_stats_are_unavailable_not_badges():
    df = hitters()
    df.loc[0, ["SO", "SO_missing"]] = [0, True]  # zero strikeouts only because none were recorded
    df.loc[1, ["SB", "CS", "CS_missing"]] = [80, 0, True]
    out = badges.hitter_badges(df)
    assert "Bat-to-Ball" not in names(out, df.loc[0, "playerID"])
    assert any(u["name"] == "Bat-to-Ball" for u in out.loc[0, "badges_unavailable"])
    assert "Base Thief" not in names(out, df.loc[1, "playerID"])
    assert any(u["name"] == "Base Thief" for u in out.loc[1, "badges_unavailable"])


def test_base_thief_needs_rate_success_and_attempts():
    df = hitters()
    df.loc[0, ["SB", "CS"]] = [70, 8]  # fast and efficient
    df.loc[1, ["SB", "CS"]] = [70, 60]  # fast, caught constantly
    df.loc[2, ["SB", "CS"]] = [12, 0]  # perfect, under the attempt floor
    out = badges.hitter_badges(df)
    assert "Base Thief" in names(out, df.loc[0, "playerID"])
    assert "Base Thief" not in names(out, df.loc[1, "playerID"])
    assert "Base Thief" not in names(out, df.loc[2, "playerID"])


def test_small_pools_award_no_percentile_badges():
    df = hitters(n=badges.BADGE_MIN_POOL - 1)
    df.loc[0, "HR"] = 70
    assert not badges.hitter_badges(df)["badges"].map(len).any()


def test_iron_man_must_be_sustained():
    seasons = pd.concat([hitters(year=y, seed=y) for y in (1990, 1991, 1992)], ignore_index=True)
    durable, once = seasons.loc[0, "playerID"], seasons.loc[1, "playerID"]
    for y in (1990, 1991, 1992):
        seasons.loc[(seasons["yearID"] == y) & (seasons.index % 40 == 0), ["playerID", "G"]] = [durable, 162]
    seasons.loc[1, "G"] = 162  # one iron season only
    out = badges.hitter_badges(seasons)
    assert all("Iron Man" in [b["name"] for b in bs] for bs in out.loc[out["playerID"] == durable, "badges"])
    assert "Iron Man" not in names(out, once)


def pitchers(n=40):
    rng = np.random.default_rng(1)
    starter = np.arange(n) < n // 2
    ip = np.where(starter, rng.uniform(150, 230, n), rng.uniform(50, 80, n))
    bf = ip * 4.2
    return pd.DataFrame({
        "playerID": [f"p{i}" for i in range(n)], "yearID": 2000, "lgID": "AL", "teamID": "T",
        "G": np.where(starter, 32, 65), "GS": np.where(starter, 32, 0), "IP": ip, "BFP": bf.astype(int),
        "H": (bf * 0.22).astype(int), "BB": (bf * 0.08).astype(int), "HBP": 3, "SO": (bf * 0.18).astype(int),
        "HR": (bf * 0.025).astype(int), "ERAplus": rng.uniform(80, 130, n), "teamG": 162,
        "slots": [{"SP"} if s else {"RP"} for s in starter],
    })


def test_pitcher_badges_and_the_reliever_only_pool():
    df = pitchers()
    df.loc[0, "ERAplus"] = 300  # a starter: never eligible for Bullpen Weapon
    df.loc[25, "ERAplus"] = 280  # a reliever
    df.loc[1, "SO"] = int(df.loc[1, "BFP"] * 0.4)
    out = badges.pitcher_badges(df)
    assert "Bullpen Weapon" not in names(out, "p0")
    assert "Bullpen Weapon" in names(out, "p25")
    assert "Strikeout Artist" in names(out, "p1")
    assert out["badges_unavailable"].map(lambda u: any(x["name"] == "Groundball Machine" for x in u)).all()
    assert not out["badges"].map(lambda bs: any(b["name"] == "Groundball Machine" for b in bs)).any()


def test_each_badge_adds_the_same_runs_in_the_season_sim():
    roster = Roster()
    hitter = {"playerID": "", "name": "", "slots": {"C", "1B", "2B", "3B", "SS", "OF", "DH"}, "wRAA": 0.0, "PA": 600, "badges": []}
    pitcher = {"playerID": "", "name": "", "slots": {"SP", "RP"}, "runs_saved": 0.0, "IP": 100, "badges": []}
    for i, label in enumerate(ALL_SLOTS):
        card = dict(hitter if label not in ("SP", "RP") else pitcher, playerID=f"x{i}")
        if i == 0:
            card["badges"] = [{"key": "slugger"}, {"key": "gap_power"}]
        if label == "SP" and i == 9:
            card["badges"] = [{"key": "workhorse"}]
        roster.assign(card, label)
    result = season.simulate(roster)
    assert result.lineup_badge_runs == 2 * badges.BADGE_RUNS
    assert result.staff_badge_runs == badges.BADGE_RUNS
    assert result.projected_runs_scored == 700 + 2 * badges.BADGE_RUNS
    assert result.projected_runs_allowed == 700 - badges.BADGE_RUNS
