"""
Phase 3 checklist - Daily Mode game loop (docs: daily-mode-loop-spec.md, section 9).

  - career rates: famous careers' totals match known numbers
  - determinism: same lineup + staff always gives the same score
  - par: stored per lineup; a strong staff beats it, a random one usually doesn't
  - spread: the score distribution across random staffs is wide enough to matter
  - power lever: a low-HR staff beats a higher-quality, HR-prone staff in some cases
  - breakdown: raw quality + matchup edge add back up to the score
  - the ranked score never depends on the sampled reveal
The log5 property tests live in tests/test_matchup.py (python -m pytest tests).

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
KNOWN_CAREERS = {  # playerID: (career HR, career SO) from Baseball-Reference
    "aaronha01": ("HR_total", 755),
    "bondsba01": ("HR_total", 762),
    "ruthba01": ("HR_total", 714),
}
KNOWN_PITCHERS = {"johnswa01": 3509, "maddugr01": 3371, "martipe02": 3154}


def check_careers(challenge: d.DailyChallenge):
    print("=== Career rates ===")
    for pid, (col, expected) in KNOWN_CAREERS.items():
        assert challenge.batters.loc[pid, col] == expected, f"{pid} career {col} is off"
    for pid, expected in KNOWN_PITCHERS.items():
        assert challenge.pitchers.loc[pid, "SO_total"] == expected, f"{pid} career strikeouts are off"
    b = challenge.batters
    print("Career totals match: Aaron 755 HR, Bonds 762, Ruth 714; Johnson 3509 K, Maddux 3371, Pedro 3154.")
    for pid in ["ruthba01", "bondsba01", "aaronha01", "judgeaa01"]:
        r = b.loc[pid]
        print(f"  {r['name']}: raw HR/PA {r['HR_total'] / r['PA']:.3f} -> modern-adjusted {r['HR']:.3f}")


def check_scoring(challenge: d.DailyChallenge):
    print("\n=== Determinism, par, breakdown ===")
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
    assert abs(first["averageStaff"] - first["rawQuality"] - first["matchupEdge"] - first["score"]) < 1e-9
    print("Same staff -> same score (in any draft order); score is the RNG-free expected value; breakdown adds up.")

    scores = sorted(challenge.simulate(TODAY, list(s))["score"] for s in staffs)
    beat = sum(s < lineup["par"] for s in scores)
    assert scores[0] < lineup["par"] < scores[-1], "Par should sit inside today's range of possible staffs"
    print(f"Today's pool: {len(scores)} possible staffs, best {scores[0]:.2f}, worst {scores[-1]:.2f}, "
          f"par {lineup['par']:.2f} -> {beat} beat par ({beat / len(scores):.0%}).")


def check_spread(challenge: d.DailyChallenge):
    print("\n=== Score distribution per lineup (random elite staffs, from calibration) ===")
    for lineup in challenge.lineups:
        assert lineup["std"] > 0.1, "Spread too narrow for a leaderboard to mean much"
        names = ", ".join(challenge.batters.loc[p, "name"].split()[-1] for p in lineup["players"])
        print(f"Lineup {lineup['id']} ({names}): par {lineup['par']:.2f}, mean {lineup['mean']:.2f}, "
              f"sd {lineup['std']:.2f}, best {lineup['best']:.2f}, worst {lineup['worst']:.2f}")


def check_power_lever(challenge: d.DailyChallenge):
    print("\n=== Theme lever: home-run suppression ===")
    env = challenge.env
    lineup = challenge.lineups[0]
    legends = [d.to_batter(challenge.batters.loc[p]) for p in lineup["players"]]
    average_lineup = [average_batter(env)] * d.LINEUP_SIZE
    rng = random.Random("lever-check")
    staffs = [rng.sample(challenge.elite_pool, d.STAFF_SIZE) for _ in range(300)]
    rows = []
    for ids in staffs:
        staff = [d.to_pitcher(challenge.pitchers.loc[p]) for p in ids]
        rows.append((
            runs.expected_runs(average_lineup, staff, env)["total"],  # raw quality (lower = better)
            runs.expected_runs(legends, staff, env)["total"],  # today's score
            np.mean([p.rates["HR"] for p in staff]),
        ))
    flips = sum(
        1 for a, b in itertools.combinations(rows, 2)
        for better, worse in ((a, b), (b, a))
        if better[0] < worse[0] and better[1] > worse[1] and worse[2] < better[2]
    )
    pairs = len(rows) * (len(rows) - 1) // 2
    assert flips > 0, "A low-HR staff never beats a better-overall, HR-prone staff: the power lever isn't working"
    print(f"{flips} of {pairs} staff pairs ({flips / pairs:.1%}): the staff with better raw quality loses to the Legends "
          f"because the other staff allows fewer home runs.")


if __name__ == "__main__":
    challenge = d.DailyChallenge()
    check_careers(challenge)
    check_scoring(challenge)
    check_spread(challenge)
    check_power_lever(challenge)
    print("\nPhase 3 (Daily Mode loop) check passed.")
