"""
Phase 2 checklist - Classic Mode: Draft + Season Simulation.

Runs a seeded, scripted spin draft (always takes the best card that fits an
open slot) so the mechanics can be verified without a human at the keyboard,
and checks off each roadmap item:
  - spin a franchise/decade each pick; every card is that player's peak
    season with that franchise in that decade
  - position eligibility rules enforced, with real positional-adjustment
    values from the Phase 1 engine (not an arbitrary flat penalty)
  - pitching staff sub-draft (rotation + bullpen), scored the same
    transparent way as batters
  - season simulation via the Pythagorean win-expectation formula
  - a scorecard showing the math, not just the final record

Usage:
    python scripts/phase2_check.py
"""

import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball import data, season
from warball.constants import POSITIONAL_ADJUSTMENT_PER_600PA
from warball.draft import PEAK_KEYS, DraftPool, Spin
from warball.eligibility import ALL_SLOTS, LINEUP_SLOTS
from warball.roster import Roster

pd.set_option("display.width", 140)

SEED = 2026


def auto_draft(pool: DraftPool) -> tuple[Roster, list]:
    rng = random.Random(SEED)
    roster = Roster()
    picks = []
    while not roster.is_complete():
        spin = pool.spin(rng)
        hitters, pitchers = pool.roster_for(spin, roster.drafted_player_ids())
        fitting = [c for c in hitters.to_dict("records") + pitchers.to_dict("records") if roster.slots_for(c)]
        if not fitting:
            continue
        card = fitting[0]
        slot = roster.slots_for(card)[0]
        roster.assign(card, slot)
        picks.append((spin, card, slot))
    return roster, picks


def check_card_pool(pool: DraftPool):
    print("=== Card pool ===")
    for cards in (pool.hitters, pool.pitchers):
        assert not cards.duplicated(PEAK_KEYS).any(), "A player has more than one card for the same team-decade"

    depth = pool.wheel.merge(
        pool.hitters.groupby(["franchID", "decade"]).size().rename("hitters").reset_index(), how="left"
    ).merge(pool.pitchers.groupby(["franchID", "decade"]).size().rename("pitchers").reset_index(), how="left")
    depth = depth.fillna(0)
    assert ((depth["hitters"] + depth["pitchers"]) > 0).all(), "A spinnable team-decade has no cards at all"
    one_sided = depth[(depth["hitters"] == 0) | (depth["pitchers"] == 0)]
    print(f"{len(pool.wheel)} spinnable team-decades, all draftable; median roster {depth['hitters'].median():.0f} hitters / {depth['pitchers'].median():.0f} pitchers.")
    print(f"{len(one_sided)} fragmentary-record clubs only offer one side: {', '.join(one_sided['label'])}")


def check_small_samples(pool: DraftPool):
    print("\n=== Small samples vs. the sim-value leaderboard ===")
    on_wheel = lambda cards: cards[cards.set_index(["franchID", "decade"]).index.isin(set(zip(pool.wheel.franchID, pool.wheel.decade)))]
    hitters = on_wheel(pool.hitters).assign(sim=lambda d: d.wRAA / d.PA * 650).nlargest(25, "sim")
    pitchers = on_wheel(pool.pitchers).assign(sim=lambda d: d.runs_saved / d.IP * 200).nlargest(25, "sim")
    assert (hitters["PA"] >= 100).all(), "A sub-100-PA season is back in the top 25 hitters"
    short_pitchers = pitchers[pitchers["IP"] < 30]
    assert (short_pitchers["teamG"] >= 60).all(), "A fragmentary-record pitcher is back in the top 25"
    print(f"Top hitter: {hitters.iloc[0]['name']} {hitters.iloc[0]['yearID']} ({hitters.iloc[0]['PA']:.0f} PA); "
          f"top pitcher: {pitchers.iloc[0]['name']} {pitchers.iloc[0]['yearID']} ({pitchers.iloc[0]['IP']:.0f} IP).")
    print(f"Top-25 pitchers under 30 IP: {len(short_pitchers)}, all from full {sorted(set(short_pitchers.teamG))}-game seasons.")


def check_known_cases(pool: DraftPool):
    print("\n=== Known cases ===")
    batting = data.load_batting()

    hitters, _ = pool.roster_for(Spin("CHC", 2020, "2020s Chicago Cubs", "Chicago Cubs"))
    bryant = hitters[hitters["playerID"] == "bryankr01"].iloc[0]
    cubs_2021_pa = batting[(batting.playerID == "bryankr01") & (batting.yearID == 2021) & (batting.teamID == "CHN")]
    cubs_2021_pa = (cubs_2021_pa["AB"] + cubs_2021_pa["BB"] + cubs_2021_pa["HBP"] + cubs_2021_pa["SF"]).sum()
    assert bryant["yearID"] == 2021, f"2020s Cubs Kris Bryant should be his 2021, got {bryant['yearID']}"
    assert bryant["PA"] == cubs_2021_pa, "Bryant's 2021 card should only count his Cubs PA, not his Giants stint"
    print(f"2020s Cubs Kris Bryant -> {bryant['yearID']} ({bryant['PA']:.0f} PA with CHC only), not his 2016 peak.")

    hitters, _ = pool.roster_for(Spin("BOS", 2000, "2000s Boston Red Sox", "Boston Red Sox"))
    ortiz = hitters[hitters["playerID"] == "ortizda01"].iloc[0]
    assert "DH" in ortiz["slots"], "A pure DH must be draftable at DH"
    print(f"2000s Red Sox David Ortiz -> {ortiz['yearID']}, eligible at {sorted(ortiz['slots'])}.")

    covid = pool.hitters[pool.hitters["yearID"] == 2020]
    assert not covid.empty, "60-game 2020 seasons should still produce qualifying cards"
    print(f"{len(covid)} hitter cards from the 60-game 2020 season qualify.")

    hitters, pitchers = pool.roster_for(Spin("PC", 1930, "1930s Pittsburgh Crawfords", "Pittsburgh Crawfords"))
    assert not hitters.empty and not pitchers.empty, "Negro League rosters should have cards"
    print(f"1930s Pittsburgh Crawfords top cards: {hitters.iloc[0]['name']} ({hitters.iloc[0]['yearID']}), "
          f"{pitchers.iloc[0]['name']} ({pitchers.iloc[0]['yearID']}).")

    hitters, _ = pool.roster_for(Spin("SFG", 1950, "1950s New York Giants", "New York Giants"))
    mays = hitters[hitters["playerID"] == "mayswi01"].iloc[0]
    hitters, _ = pool.roster_for(Spin("NYY", 1920, "1920s New York Yankees", "New York Yankees"))
    ruth = hitters[hitters["playerID"] == "ruthba01"].iloc[0]
    assert mays["cf"] and not ruth["cf"], "Center-field flag should mark Mays (CF) but not Ruth (corner OF)"
    print(f"Center fielders: Mays {mays['yearID']} is OF/CF, Ruth {ruth['yearID']} is plain OF.")

    managers = pool.managers_for(Spin("BAL", 1970, "1970s Baltimore Orioles", "Baltimore Orioles"))
    weaver = managers[managers["playerID"] == "weaveea99"].iloc[0]
    assert weaver["W"] + weaver["L"] >= 162, "Coach cards need a full season of games managed"
    print(f"1970s Orioles coach Earl Weaver: {weaver['W']:.0f}-{weaver['L']:.0f}, "
          f"{weaver['wins_vs_pythag']:+.1f} wins vs. Pythagorean per 162.")


def check_spin_rules(pool: DraftPool, picks: list):
    print("\n=== Spin draft rules ===")
    for spin, card, slot in picks:
        assert card["franchID"] == spin.franchID, f"{card['name']} isn't from the spun franchise"
        assert spin.decade <= card["yearID"] < spin.decade + 10, f"{card['name']} isn't from the spun decade"
        assert slot in card["slots"], f"{card['name']} placed at {slot} without eligibility"

        is_hitter = slot in LINEUP_SLOTS
        seasons, value = (pool.hitter_seasons, "WAR") if is_hitter else (pool.pitcher_seasons, "runs_saved")
        same = seasons[
            (seasons.playerID == card["playerID"]) & (seasons.franchID == spin.franchID) & (seasons.decade == spin.decade)
        ]
        assert card[value] == same[value].max(), f"{card['name']} card isn't their peak season for {spin.label}"
    print(f"All {len(picks)} picks came from their spun team-decade, at their peak season there, in an eligible slot.")


def check_roster_rules(roster: Roster):
    print("\n=== Roster rules ===")
    assert roster.is_complete(), "Roster incomplete after auto-draft"
    ids = [card["playerID"] for card in roster.filled.values()]
    assert len(ids) == len(set(ids)), "Same player drafted twice - uniqueness rule broken"

    rates = {}
    for card in roster.lineup:
        rate = card["pos_adj_runs"] / card["PA"] * 600
        assert abs(rate - POSITIONAL_ADJUSTMENT_PER_600PA[card["POS"]]) < 1e-6, f"{card['name']} positional adjustment is off"
        rates[card["POS"]] = round(rate, 2)
    print(f"{len(ALL_SLOTS)} slots filled, all players unique. Positional adjustment runs/600 PA used: {rates}")


def print_scorecard(roster: Roster, picks: list, result: season.SeasonResult):
    print("\n=== Scorecard (the math, not just the record) ===")
    for spin, card, slot in picks:
        if slot in LINEUP_SLOTS:
            stats = f"wOBA {card['wOBA']:.3f}  OPS+ {card['OPSplus']:.0f}  WAR {card['WAR']:.1f}"
        else:
            stats = f"FIP {card['FIP']:.2f}  ERA+ {card['ERAplus']:.0f}  runs saved {card['runs_saved']:+.1f}"
        print(f"  {slot:<3} {card['name']:<22} {card['yearID']}  [{spin.label}]  {stats}")

    print(f"\n  Lineup wRAA (full season):     {result.lineup_wraa_full_season:+.1f}")
    print(f"  Projected Runs Scored:         {result.projected_runs_scored:.0f}")
    print(f"  Staff runs saved (full season): {result.staff_runs_saved_full_season:+.1f}")
    print(f"  Projected Runs Allowed:        {result.projected_runs_allowed:.0f}")
    print(f"  Pythagorean win%:              {result.win_pct:.3f}")
    print(f"  PROJECTED RECORD:              {result.wins}-{result.losses}")


if __name__ == "__main__":
    pool = DraftPool()
    check_card_pool(pool)
    check_small_samples(pool)
    check_known_cases(pool)

    roster, picks = auto_draft(pool)
    check_spin_rules(pool, picks)
    check_roster_rules(roster)

    result = season.simulate(roster)
    assert 0.0 < result.win_pct < 1.0 and result.wins + result.losses == 162, "Season sim out of range"
    print_scorecard(roster, picks, result)

    coached = season.simulate(roster, coach_wins=2.4)
    assert coached.wins == min(round(result.pythag_wins + 2.4), 162), "Coach wins should add to the Pythagorean total"
    assert season.simulate(roster, coach_wins=500).wins == 162, "Coach wins must cap at a 162-0 season"
    assert season.simulate(roster, coach_wins=-500).wins == 0, "Coach wins must floor at 0"
    print(f"\nCoach adjustment: +2.4 wins turns {result.wins}-{result.losses} into {coached.wins}-{coached.losses}; capped at 162-0.")

    print("\nPhase 2 check passed: spin draft, peak-season cards, eligibility, pitching staff, and Pythagorean sim all work.")
