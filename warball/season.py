"""
Season simulation: projects a drafted Roster to a full-season Runs Scored /
Runs Allowed, converts that to a win-loss record via the Pythagorean
win-expectation formula, then adds the coach's wins above Pythagorean
expectation. Each badge on a card (badges.py) adds BADGE_RUNS: runs scored
for a hitter, runs saved for a pitcher. Every number in SeasonResult is meant to be shown to the player,
not hidden behind a single record.
"""

from dataclasses import dataclass

from warball.badges import BADGE_RUNS
from warball.constants import (
    BATTER_SEASON_PA,
    LEAGUE_AVG_RUNS_PER_SEASON,
    PYTHAGOREAN_EXPONENT,
    ROTATION_SEASON_IP_EACH,
    SEASON_GAMES,
    SEASON_INNINGS,
)
from warball.eligibility import BULLPEN_SLOTS, ROTATION_SLOTS
from warball.roster import Roster


@dataclass
class SeasonResult:
    hitter_runs: list[float]  # each lineup card's full-season wRAA, in lineup-slot order
    pitcher_ip: list[float]  # simulated innings per staff card, rotation then bullpen
    pitcher_runs: list[float]  # each staff card's full-season runs saved, same order
    hitter_badge_runs: list[float]  # BADGE_RUNS x badges, lineup-slot order
    pitcher_badge_runs: list[float]  # BADGE_RUNS x badges, rotation then bullpen
    lineup_wraa_full_season: float
    lineup_badge_runs: float
    projected_runs_scored: float
    rotation_ip_total: float
    bullpen_ip_total: float
    staff_runs_saved_full_season: float
    staff_badge_runs: float
    projected_runs_allowed: float
    win_pct: float
    pythag_wins: float
    coach_wins: float
    wins: int
    losses: int


def _hitter_runs(roster: Roster) -> list[float]:
    """Each starter's own wRAA-per-PA rate (already era-relative) applied to a full season."""
    return [row["wRAA"] / row["PA"] * BATTER_SEASON_PA for row in roster.lineup]


def _pitcher_workloads(roster: Roster) -> tuple[list[float], list[float]]:
    """Returns (simulated IP, full-season runs saved) per staff card.

    Mirrors the lineup side: each pitcher's runs-saved-per-inning rate (FIP vs.
    their own year+league's ERA, so already era-relative) is applied to their
    simulated workload. Raw FIP would hand dead-ball and 1960s pitchers a free
    edge just for pitching in a low-scoring era.
    """
    bullpen_ip_each = (SEASON_INNINGS - ROTATION_SEASON_IP_EACH * ROTATION_SLOTS) / BULLPEN_SLOTS
    staff = [(row, ROTATION_SEASON_IP_EACH) for row in roster.rotation] + [(row, bullpen_ip_each) for row in roster.bullpen]
    ip = [workload for _, workload in staff]
    runs = [row["runs_saved"] / row["IP"] * workload for row, workload in staff]
    return ip, runs


def _badge_runs(cards: list[dict]) -> list[float]:
    return [BADGE_RUNS * len(card.get("badges") or []) for card in cards]


def simulate(roster: Roster, coach_wins: float = 0.0) -> SeasonResult:
    if not roster.is_complete():
        raise ValueError("Roster must be complete (lineup + rotation + bullpen) before simulating a season")

    hitter_runs = _hitter_runs(roster)
    lineup_wraa = sum(hitter_runs)
    hitter_badge_runs = _badge_runs(roster.lineup)
    runs_scored = LEAGUE_AVG_RUNS_PER_SEASON + lineup_wraa + sum(hitter_badge_runs)

    pitcher_ip, pitcher_runs = _pitcher_workloads(roster)
    staff_runs_saved = sum(pitcher_runs)
    pitcher_badge_runs = _badge_runs(roster.rotation + roster.bullpen)
    runs_allowed = LEAGUE_AVG_RUNS_PER_SEASON - staff_runs_saved - sum(pitcher_badge_runs)

    # The Pythagorean formula is undefined for runs <= 0 (a fractional power
    # of a negative number). A historically bad-enough lineup or pitching
    # staff could in principle drive projected runs below zero; floor it at
    # a nominal 1 run rather than let the formula blow up into NaN.
    runs_scored = max(runs_scored, 1.0)
    runs_allowed = max(runs_allowed, 1.0)

    rs_exp = runs_scored**PYTHAGOREAN_EXPONENT
    ra_exp = runs_allowed**PYTHAGOREAN_EXPONENT
    win_pct = rs_exp / (rs_exp + ra_exp)
    pythag_wins = win_pct * SEASON_GAMES
    wins = min(max(round(pythag_wins + coach_wins), 0), SEASON_GAMES)

    return SeasonResult(
        hitter_runs=hitter_runs,
        pitcher_ip=pitcher_ip,
        pitcher_runs=pitcher_runs,
        hitter_badge_runs=hitter_badge_runs,
        pitcher_badge_runs=pitcher_badge_runs,
        lineup_wraa_full_season=lineup_wraa,
        lineup_badge_runs=sum(hitter_badge_runs),
        projected_runs_scored=runs_scored,
        rotation_ip_total=ROTATION_SEASON_IP_EACH * ROTATION_SLOTS,
        bullpen_ip_total=SEASON_INNINGS - ROTATION_SEASON_IP_EACH * ROTATION_SLOTS,
        staff_runs_saved_full_season=staff_runs_saved,
        staff_badge_runs=sum(pitcher_badge_runs),
        projected_runs_allowed=runs_allowed,
        win_pct=win_pct,
        pythag_wins=pythag_wins,
        coach_wins=coach_wins,
        wins=wins,
        losses=SEASON_GAMES - wins,
    )
