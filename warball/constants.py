"""
Fixed sabermetric constants used across the stat engine.

These are widely-cited approximations, not year-by-year FanGraphs "guts"
constants (which aren't freely published for most historical seasons). Using
one fixed set of weights for all of history is a deliberate simplification:
the era-adjustment work is done separately, by comparing each player to their
own year+league's average (see league.py), not by varying these weights.
"""

# wOBA linear weights (Tom Tango's commonly-cited ~2013 constants).
WOBA_WEIGHTS = {
    "uBB": 0.690,
    "HBP": 0.722,
    "1B": 0.888,
    "2B": 1.271,
    "3B": 1.616,
    "HR": 2.101,
}

# Converts (wOBA - league wOBA) into runs above average per plate appearance.
# The real value drifts with the run environment (~1.15-1.25); fixed here.
WOBA_SCALE = 1.15

# Runs per win, used to convert runs above replacement into WAR. The real
# value drifts with the run environment (~9-10.5); fixed here.
RUNS_PER_WIN = 10.0

# Replacement level, in runs below average per 600 PA (FanGraphs convention).
REPLACEMENT_RUNS_PER_600PA = 20.0

# Positional adjustments, in runs per 600 PA (FanGraphs convention).
# Lahman's Fielding table only records a generic "OF" position rather than
# splitting LF/CF/RF, so OF gets the average of the three (-7.5, +2.5, -7.5).
POSITIONAL_ADJUSTMENT_PER_600PA = {
    "C": 12.5,
    "1B": -12.5,
    "2B": 2.5,
    "3B": 2.5,
    "SS": 7.5,
    "OF": -4.17,
    "DH": -17.5,
    "P": 0.0,
}

PA_NORM = 600.0
IP_NORM = 200.0

# --- Phase 2: season simulation ---

SEASON_GAMES = 162
SEASON_INNINGS = SEASON_GAMES * 9  # defensive innings a team's staff covers in a full season

# Assumed full-season workload per drafted slot, used to scale each player's
# per-PA/per-9-IP rate stats into a full season's worth of runs. These are
# "healthy full-time regular" numbers, not any individual season's actual
# playing time (a 1918 half-season ace projects at a full year's rate here).
BATTER_SEASON_PA = 650
ROTATION_SEASON_IP_EACH = 200  # 5 starters

# A fixed, era-neutral reference run environment (~4.3 R/G), so that runs
# above/below average from any era can be added onto a common baseline. wRAA
# and FIP are already era-relative by construction (see league.py); this
# constant is only the canvas they're painted onto.
LEAGUE_AVG_RUNS_PER_SEASON = 700.0

# Bill James' original Pythagorean exponent was 2; ~1.83 is the commonly
# cited refinement that fits actual MLB standings better.
PYTHAGOREAN_EXPONENT = 1.83
