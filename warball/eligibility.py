"""
Draft-time qualification and slot eligibility for a player-team-season.

Thresholds are a share of the team's games that season rather than a flat
count, so they scale with season length: roughly 300 PA / 100 IP / 20 games
at a position over 162 games, but proportionally less for the 60-game 2020
season, 1870s schedules (~58 games), or Negro League seasons (~45-70). Small
absolute floors (BATTER_MIN_PA, PITCHER_MIN_IP) only catch fragmentary
records. These are fantasy-baseball-style cutoffs, not from a formal source.
"""

import pandas as pd

BATTER_PA_PER_TEAM_GAME = 1.85
FIELDING_GAMES_PER_TEAM_GAME = 0.12
SP_STARTS_PER_TEAM_GAME = 0.06
SP_IP_PER_TEAM_GAME = 0.62
RP_RELIEF_APPS_PER_TEAM_GAME = 0.06
RP_IP_PER_TEAM_GAME = 0.185

# Absolute sample floors on top of the per-team-game shares. They only bind on
# team-seasons with a handful of recorded games (fragmentary early Negro League
# and independent-club records), whose regulars otherwise topped the sim-value
# leaderboard off 4-49 PA or 14 IP. Regulars in any real short season (60-game
# 2020, 1870s, full Negro League schedules) clear them easily. Picked as the
# lowest values where no top-25 hitter has under 100 PA, no fragmentary-record
# pitcher reaches the top 25, and every spinnable team-decade still has cards.
BATTER_MIN_PA = 50
PITCHER_MIN_IP = 15

# An outfielder is a center field specialist ("OF/CF") when at least half of
# their outfield games that team-season were in center.
CF_SHARE_OF_OUTFIELD_GAMES = 0.5

SEASON_KEYS = ["playerID", "yearID", "teamID"]

# The 9 lineup slots. Lahman's Fielding table only records a generic "OF"
# (not split into LF/CF/RF — see warball/constants.py), so the outfield is
# three interchangeable OF slots rather than LF/CF/RF.
LINEUP_SLOTS = ["C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "DH"]
ROTATION_SLOTS = 5
BULLPEN_SLOTS = 3
ALL_SLOTS = LINEUP_SLOTS + ["SP"] * ROTATION_SLOTS + ["RP"] * BULLPEN_SLOTS


def batter_positions(fielding, team_games):
    """Returns SEASON_KEYS + a `positions` set of every position played often enough that season."""
    played = fielding.groupby(SEASON_KEYS + ["POS"], as_index=False)["G"].sum()
    played = played.merge(team_games, on=["yearID", "teamID"])
    qualified = played[played["G"] >= FIELDING_GAMES_PER_TEAM_GAME * played["teamG"]]
    return qualified.groupby(SEASON_KEYS)["POS"].agg(set).rename("positions").reset_index()


def center_fielders(fielding_of, fielding_of_split, batting):
    """Returns SEASON_KEYS + a `cf` flag for every player-team-season with LF/CF/RF game counts.

    FieldingOFsplit (1891+) is keyed by team. The older FieldingOF (1871-1955)
    only has a stint number, which Batting's stints map to a team. Where both
    cover a season, the team-keyed split table wins.
    """
    split = fielding_of_split.pivot_table(
        index=SEASON_KEYS, columns="POS", values="G", aggfunc="sum", fill_value=0
    ).reset_index()

    old = fielding_of.merge(batting[["playerID", "yearID", "stint", "teamID"]], on=["playerID", "yearID", "stint"])
    old = (
        old.groupby(SEASON_KEYS, as_index=False)[["Glf", "Gcf", "Grf"]].sum()
        .rename(columns={"Glf": "LF", "Gcf": "CF", "Grf": "RF"})
    )

    games = pd.concat([split, old]).drop_duplicates(SEASON_KEYS, keep="first").fillna(0)
    outfield_games = games["LF"] + games["CF"] + games["RF"]
    games["cf"] = (outfield_games > 0) & (games["CF"] >= CF_SHARE_OF_OUTFIELD_GAMES * outfield_games)
    return games[SEASON_KEYS + ["cf"]]


def hitter_slots(positions) -> set:
    """Lineup slots a qualified hitter can fill. Anyone who hit enough can DH."""
    positions = positions if isinstance(positions, set) else set()
    return (positions & set(LINEUP_SLOTS)) | {"DH"}


def pitcher_slots(g, gs, ip, team_g) -> set:
    """Staff slots a pitcher-season can fill, based on how they were used and how much they threw."""
    slots = set()
    if ip < PITCHER_MIN_IP:
        return slots
    if gs >= SP_STARTS_PER_TEAM_GAME * team_g and ip >= SP_IP_PER_TEAM_GAME * team_g:
        slots.add("SP")
    if (g - gs) >= RP_RELIEF_APPS_PER_TEAM_GAME * team_g and ip >= RP_IP_PER_TEAM_GAME * team_g:
        slots.add("RP")
    return slots
