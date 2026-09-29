"""
Card tiers for the Classic draft, MLB The Show style: bronze < silver < gold < diamond.

Both scales are already era-fair, so a 1920s card and a 2010s card tier the same way:
  hitters   season WAR, on FanGraphs' rule of thumb (2 = starter, 4 = All-Star, 6 = MVP)
  pitchers  season FIP- (100 = league average, lower is better)
"""

HITTER_WAR = (("diamond", 6.0), ("gold", 4.0), ("silver", 2.0))  # at least this WAR
PITCHER_FIP_MINUS = (("diamond", 70.0), ("gold", 85.0), ("silver", 100.0))  # at most this FIP-


def hitter_tier(war: float) -> str:
    return next((tier for tier, floor in HITTER_WAR if war >= floor), "bronze")


def pitcher_tier(fip_minus: float) -> str:
    return next((tier for tier, ceiling in PITCHER_FIP_MINUS if fip_minus <= ceiling), "bronze")
