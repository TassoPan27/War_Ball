"""
Interactive Classic Mode draft - terminal version (Phase 2 CLI-first pass;
a real Draft UI comes in a later phase).

Era Ball style: each of the 17 picks spins a random franchise + decade, and
you draft one player off that roster - their peak season with that team in
that decade - into any open slot they're eligible for. Once the roster is
full it runs the season simulation and prints the full scorecard.

Usage:
    python scripts/cli_draft.py
"""

import random
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball import season
from warball.badges import BADGE_RUNS
from warball.draft import DraftPool
from warball.eligibility import ALL_SLOTS, LINEUP_SLOTS
from warball.roster import Roster

pd.set_option("display.width", 140)


def with_fits(cards: pd.DataFrame, roster: Roster) -> pd.DataFrame:
    """Adds a `fits` column (open slots each card can fill) and drops cards that fit nowhere."""
    cards = cards.copy()
    cards["fits"] = ["/".join(roster.slots_for(card)) for card in cards.to_dict("records")]
    return cards[cards["fits"] != ""]


def spin_until_draftable(pool: DraftPool, roster: Roster, rng: random.Random):
    while True:
        spin = pool.spin(rng)
        hitters, pitchers = pool.roster_for(spin, roster.drafted_player_ids())
        hitters, pitchers = with_fits(hitters, roster), with_fits(pitchers, roster)
        if not hitters.empty or not pitchers.empty:
            return spin, hitters, pitchers
        print(f"  (spun {spin.label} - nobody left who fits your open slots, spinning again)")


def describe_open_slots(roster: Roster) -> str:
    counts = Counter(roster.open_slot_labels())
    ordered = dict.fromkeys(label for label in ALL_SLOTS if label in counts)
    return ", ".join(label if counts[label] == 1 else f"{label} x{counts[label]}" for label in ordered)


def show_cards(hitters: pd.DataFrame, pitchers: pd.DataFrame):
    if not hitters.empty:
        h = hitters[["name", "yearID", "fits", "PA", "HR", "OPSplus", "WAR"]].copy()
        h.insert(0, "#", range(1, len(h) + 1))
        print(h.to_string(index=False, formatters={"PA": "{:.0f}".format, "OPSplus": "{:.0f}".format, "WAR": "{:.1f}".format}))
    if not pitchers.empty:
        p = pitchers[["name", "yearID", "fits", "IP", "FIP", "ERAplus", "runs_saved"]].copy()
        p.insert(0, "#", range(len(hitters) + 1, len(hitters) + len(p) + 1))
        print(p.to_string(index=False, formatters={
            "IP": "{:.0f}".format, "FIP": "{:.2f}".format, "ERAplus": "{:.0f}".format, "runs_saved": "{:+.1f}".format,
        }))


def prompt_number(prompt: str, count: int) -> int:
    while True:
        choice = input(prompt).strip()
        if choice.isdigit() and 1 <= int(choice) <= count:
            return int(choice) - 1
        print(f"Enter a number from 1 to {count}.")


def run_draft():
    pool = DraftPool()
    roster = Roster()
    rng = random.Random()

    while not roster.is_complete():
        pick_number = len(roster.filled) + 1
        spin, hitters, pitchers = spin_until_draftable(pool, roster, rng)

        print(f"\n=== Pick {pick_number}/{len(ALL_SLOTS)}: {spin.label} ===")
        print(f"Open slots: {describe_open_slots(roster)}")
        show_cards(hitters, pitchers)

        cards = hitters.to_dict("records") + pitchers.to_dict("records")
        card = cards[prompt_number("Draft #: ", len(cards))]

        options = roster.slots_for(card)
        if len(options) == 1:
            slot = options[0]
        else:
            listing = "  ".join(f"{i}) {label}" for i, label in enumerate(options, 1))
            slot = options[prompt_number(f"Slot for {card['name']}? {listing}: ", len(options))]

        roster.assign(card, slot)
        print(f"Drafted {card['name']} ({card['yearID']} {card['team_name']}) at {slot}")

    print_scorecard(roster)


def print_scorecard(roster: Roster):
    print("\n" + "=" * 60)
    print("FINAL ROSTER")
    print("=" * 60)
    for pos, r in zip(LINEUP_SLOTS, roster.lineup):
        print(f"  {pos:<3} {r['name']:<22} {r['yearID']} {r['team_name']:<24} WAR {r['WAR']:.1f}  OPS+ {r['OPSplus']:.0f}")
    print("  Rotation:")
    for r in roster.rotation:
        print(f"    SP  {r['name']:<22} {r['yearID']} {r['team_name']:<24} FIP {r['FIP']:.2f}  ERA+ {r['ERAplus']:.0f}")
    print("  Bullpen:")
    for r in roster.bullpen:
        print(f"    RP  {r['name']:<22} {r['yearID']} {r['team_name']:<24} FIP {r['FIP']:.2f}  ERA+ {r['ERAplus']:.0f}")

    result = season.simulate(roster)
    print("\n" + "=" * 60)
    print("SEASON PROJECTION - the math, not just a record")
    print("=" * 60)
    print(f"  Lineup wRAA (full-season rate x 650 PA/starter): {result.lineup_wraa_full_season:+.1f} runs")
    print(f"  Hitter badges ({BADGE_RUNS:.0f} runs each):                  {result.lineup_badge_runs:+.1f} runs")
    print(f"  Projected Runs Scored (700 + wRAA + badges):      {result.projected_runs_scored:.0f}")
    print(f"  Rotation innings (5 x 200):                       {result.rotation_ip_total:.0f}")
    print(f"  Bullpen innings (season remainder / 3):           {result.bullpen_ip_total:.0f}")
    print(f"  Staff runs saved (per-IP rate x simulated IP):    {result.staff_runs_saved_full_season:+.1f} runs")
    print(f"  Pitcher badges ({BADGE_RUNS:.0f} runs each):                 {result.staff_badge_runs:+.1f} runs")
    print(f"  Projected Runs Allowed (700 - saved - badges):    {result.projected_runs_allowed:.0f}")
    print(f"  Pythagorean win% (exponent 1.83):                 {result.win_pct:.3f}")
    print(f"\n  PROJECTED RECORD: {result.wins}-{result.losses}")


if __name__ == "__main__":
    try:
        run_draft()
    except (KeyboardInterrupt, EOFError):
        print("\nDraft cancelled.")
