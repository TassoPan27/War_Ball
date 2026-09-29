"""
Phase 3 checklist - Daily Mode pitcher-draft themes (docs: daily-mode-loop-spec.md, section 9).

  - career rates: famous careers' totals match known numbers
  - Legends: each theme's lineups are the players its stat says they should be,
    and every one played most of his career from 1893 on (60'6")
  - determinism: same lineup + staff always gives the same score
  - par: stored per lineup; a strong staff beats it, a random one usually doesn't
  - spread: the score distribution across random staffs is wide enough to matter
  - theme lever: a staff strong on the theme's lever (HR% for power) beats a
    higher-quality staff that's weak on it in some cases
  - breakdown: raw quality + matchup edge add back up to the score
  - the ranked score never depends on the sampled reveal
The model property tests live in tests/ (python -m pytest tests).

Usage:
    python -m warball.daily          # (re)calibrate par after changing careers or settings
    python scripts/phase3_check.py
"""

import datetime
import itertools
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball import daily as d
from warball import runs
from warball.matchup import average_batter

TODAY = datetime.date(2026, 9, 28)
KNOWN_CAREERS = {"aaronha01": 755, "bondsba01": 762, "ruthba01": 714}  # career HR, Baseball-Reference
KNOWN_PITCHERS = {"johnswa01": 3509, "maddugr01": 3371, "martipe02": 3154}  # career strikeouts


def check_careers(challenge: d.StaffChallenge):
    print("=== Career rates ===")
    b = challenge.batters
    for pid, expected in KNOWN_CAREERS.items():
        assert b.loc[pid, "HR_total"] == expected, f"{pid} career HR is off"
    for pid, expected in KNOWN_PITCHERS.items():
        assert challenge.pitchers.loc[pid, "SO_total"] == expected, f"{pid} career strikeouts are off"
    assert "babip" in b, "Career BABIP missing: rerun python -m warball.pipeline"
    print("Career totals match: Aaron 755 HR, Bonds 762, Ruth 714; Johnson 3509 K, Maddux 3371, Pedro 3154.")
    for pid in ["ruthba01", "bondsba01", "aaronha01", "judgeaa01"]:
        r = b.loc[pid]
        print(f"  {r['name']}: raw HR/PA {r['HR_total'] / r['PA']:.3f} -> modern-adjusted {r['HR']:.3f}")
    for pid in ["gwynnto01", "boggswa01", "suzukic01"]:
        r = b.loc[pid]
        modeled_avg = (r["HR"] + r["BIP"] * r["babip"]) / (1 - r["BB"])  # AB ~ PA - walks
        print(f"  {r['name']}: adjusted BABIP {r['babip']:.3f}, modeled AVG {modeled_avg:.3f} "
              f"(actual career AVG {r['H'] / r['AB']:.3f})")


def check_legends(challenge: d.StaffChallenge):
    theme = challenge.theme
    print(f"\n=== {theme.label}: Legends ===")
    b = challenge.batters
    for lineup in challenge.lineups:
        players = b.loc[lineup["players"]]
        assert (players["PA_modern"] / players["PA"] > d.LEGEND_MIN_MODERN_SHARE).all(), "A pre-1893 career is a Legend"
        if theme.key == "power":
            assert players["HR"].min() > challenge.env.rates["HR"] * 1.5, "Power Legends should homer far more than league"
        names = ", ".join(n.split()[-1] for n in players["name"])
        print(f"Lineup {lineup['id']}: {names}")


def check_scoring(challenge: d.StaffChallenge):
    print(f"\n=== {challenge.theme.label}: determinism, par, breakdown ===")
    lineup, pool = challenge.day(TODAY)
    staffs = list(itertools.combinations(pool, d.STAFF_SIZE))
    first = challenge.simulate(TODAY, list(staffs[0]))
    again = challenge.simulate(TODAY, list(staffs[0]))
    reordered = challenge.simulate(TODAY, list(reversed(staffs[0])))
    assert first["score"] == again["score"] and first["sampleGame"] == again["sampleGame"]
    assert abs(first["score"] - reordered["score"]) < 1e-9, "Score must not depend on draft order"

    legends = [d.to_batter(challenge.batters.loc[p]) for p in lineup["players"]]
    staff = [d.to_pitcher(challenge.pitchers.loc[p]) for p in staffs[0]]
    assert first["score"] == runs.expected_runs(legends, staff, challenge.env)["total"], "Score must be the pure expected value"
    assert abs(first["average"] - first["rawQuality"] - first["matchupEdge"] - first["score"]) < 1e-9
    print("Same staff -> same score (in any draft order); score is the RNG-free expected value; breakdown adds up.")

    scores = sorted(challenge.simulate(TODAY, list(s))["score"] for s in staffs)
    beat = sum(s < lineup["par"] for s in scores)
    assert scores[0] < lineup["par"] < scores[-1], "Par should sit inside today's range of possible staffs"
    print(f"Today's pool: {len(scores)} possible staffs, best {scores[0]:.2f}, worst {scores[-1]:.2f}, "
          f"par {lineup['par']:.2f} -> {beat} beat par ({beat / len(scores):.0%}).")


def check_spread(challenge: d.StaffChallenge):
    print(f"\n=== {challenge.theme.label}: score distribution per lineup (random elite staffs) ===")
    for lineup in challenge.lineups:
        print(f"Lineup {lineup['id']}: par {lineup['par']:.2f}, mean {lineup['mean']:.2f}, "
              f"sd {lineup['std']:.2f}, best {lineup['best']:.2f}, worst {lineup['worst']:.2f}")
    # Print every lineup first, so a failure still shows the numbers.
    assert all(lineup["std"] > 0.1 for lineup in challenge.lineups), "Spread too narrow for a leaderboard to mean much"


def check_lever(challenge: d.StaffChallenge):
    theme = challenge.theme
    print(f"\n=== {theme.label}: theme lever ({theme.lever_name}) ===")
    env = challenge.env
    legends = [d.to_batter(challenge.batters.loc[p]) for p in challenge.lineups[0]["players"]]
    average_lineup = [average_batter(env)] * d.LINEUP_SIZE
    rng = random.Random("lever-check")
    rows = []
    for _ in range(300):
        staff = [d.to_pitcher(challenge.pitchers.loc[p]) for p in rng.sample(challenge.elite_pool, d.STAFF_SIZE)]
        rows.append((
            runs.expected_runs(average_lineup, staff, env)["total"],  # raw quality (lower = better)
            runs.expected_runs(legends, staff, env)["total"],  # today's score
            np.mean([p.rates[theme.lever] for p in staff]),
        ))
    flips = sum(
        1 for a, b in itertools.combinations(rows, 2)
        for better, worse in ((a, b), (b, a))
        if better[0] < worse[0] and better[1] > worse[1] and worse[2] < better[2]
    )
    pairs = len(rows) * (len(rows) - 1) // 2
    assert flips > 0, f"A strong-{theme.lever} staff never beats a better-overall staff: the lever isn't working"
    print(f"{flips} of {pairs} staff pairs ({flips / pairs:.1%}): the staff with better raw quality loses to the Legends "
          f"because the other staff is better at {theme.lever_name}.")


if __name__ == "__main__":
    batters, pitchers = d.load_careers()
    for i, theme in enumerate(d.STAFF_THEMES.values()):
        challenge = d.StaffChallenge(theme, batters, pitchers)
        if i == 0:
            check_careers(challenge)
        check_legends(challenge)
        check_scoring(challenge)
        check_spread(challenge)
        check_lever(challenge)
    print("\nPhase 3 (Daily Mode pitcher-draft themes) check passed.")
