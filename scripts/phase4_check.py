"""
Phase 4 checklist - Daily Mode Theme C: Great Pitchers (Statcast, 2015-2024).

  - data: the Statcast pull covers every season with a sane number of plate appearances
  - Kershaw sanity check: the model finds the curveball as his signature pitch,
    matching every scouting report (the roadmap's riskiest assumption)
  - aces: the pitchers chosen are recognizable aces, each with a real signature pitch
  - determinism: same lineup always gives the same score; breakdown adds up
  - par: a strong lineup beats it, a random one usually doesn't; the spread matters
  - theme lever: a lineup that handles the ace's signature pitch beats a
    better-overall lineup in some cases

Usage:
    python -m warball.statcast       # pull (resumable) + aggregate Statcast
    python -m warball.aces           # choose aces, calibrate par
    python scripts/phase4_check.py
"""

import datetime
import itertools
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball import aces as a
from warball import arsenal, statcast
from warball.arsenal import GROUP_NAMES, GROUPS

TODAY = datetime.date(2026, 9, 30)
KERSHAW = 477132  # MLBAM id
MIN_SEASON_PA, MAX_SEASON_PA = 60_000, 200_000  # 2020's 60-game season ~66k; full seasons ~180k


def check_data():
    print("=== Statcast coverage ===")
    pitches = statcast.load_pitches()
    pa = pitches[pitches["outcome"].notna()].groupby("year").size()
    for year, n in pa.items():
        assert MIN_SEASON_PA <= n <= MAX_SEASON_PA, f"{year} has {n:,} plate appearances: incomplete pull?"
    print("  ".join(f"{y}: {n:,}" for y, n in pa.items()))


def check_kershaw(challenge: a.AceChallenge):
    print("\n=== Kershaw sanity check ===")
    rows = pd.read_csv(statcast.PITCHERS_FILE)
    rows = rows[rows["player"] == KERSHAW]
    assert not rows.empty, "Kershaw missing from the Statcast pitchers"
    groups = {r["group"]: r.to_dict() for _, r in rows.iterrows()}
    model = arsenal.fit_pitcher(groups, challenge.env)
    avg_batter, avg_pitcher = arsenal.average_batter(challenge.env), arsenal.average_pitcher(challenge.env)
    for g in GROUPS:
        c = groups.get(g)
        whiff = c["whiffs"] / c["swings"] if c is not None and c["swings"] else float("nan")
        print(f"  {GROUP_NAMES[g]:>9}: {model.usage[g]:5.1%} of PA, whiff {whiff:5.1%}, wOBA "
              f"{a.group_woba(avg_batter, model, challenge.env, g):.3f} vs lg {a.group_woba(avg_batter, avg_pitcher, challenge.env, g):.3f}")
    sig = a.signature_group(model, challenge.env)
    assert sig == "CU", f"Kershaw's signature came out as his {GROUP_NAMES[sig]}, not his curveball"
    print("Signature pitch: curveball, matching the scouting reports.")


def check_aces(challenge: a.AceChallenge):
    print("\n=== Aces ===")
    for ace in challenge.aces:
        g = ace["groups"][ace["signature"]]
        assert ace["wobaAllowed"] < challenge._ace_card(ace)["leagueWoba"], f"{ace['name']} isn't better than league"
        assert g["woba"] < g["leagueWoba"], f"{ace['name']}'s signature pitch doesn't beat the league"
        print(f"{ace['name']} ({ace['years']}): wOBA allowed {ace['wobaAllowed']:.3f}; signature "
              f"{GROUP_NAMES[ace['signature']]} ({g['usage']:.0%} of PA, {g['woba']:.3f} vs lg {g['leagueWoba']:.3f}); "
              f"par {ace['par']:.2f}, random lineups mean {ace['mean']:.2f}, sd {ace['std']:.2f}")
        assert ace["std"] > 0.05, "Spread too narrow for a leaderboard to mean much"


def check_scoring(challenge: a.AceChallenge):
    print("\n=== Determinism, par, breakdown ===")
    ace, pool = challenge.day(TODAY)
    picks = pool[: a.LINEUP_SIZE]
    first = challenge.simulate(TODAY, picks)
    assert first == challenge.simulate(TODAY, picks), "Same lineup must give the same result"
    assert abs(first["average"] + first["rawQuality"] + first["matchupEdge"] - first["score"]) < 1e-9
    assert abs(sum(h["runs"] for h in first["hitters"]) - first["score"]) < 1e-9
    print("Same lineup -> same score and reveal; breakdown and per-hitter runs add up.")

    rng = random.Random("phase4-scoring")
    scores = sorted(challenge.simulate(TODAY, rng.sample(pool, a.LINEUP_SIZE))["score"] for _ in range(200))
    beat = sum(s > ace["par"] for s in scores)
    assert scores[0] < ace["par"] < scores[-1], "Par should sit inside today's range of possible lineups"
    print(f"Today ({ace['name']}): 200 random lineups from the pool, worst {scores[0]:.2f}, best {scores[-1]:.2f}, "
          f"par {ace['par']:.2f} -> {beat} beat par ({beat / len(scores):.0%}).")


def check_lever(challenge: a.AceChallenge):
    print("\n=== Theme lever: handling the signature pitch ===")
    ace = next((x for x in challenge.aces if x["signature"] == "CU"), challenge.aces[0])
    model, sig, env = challenge._ace_model(ace), ace["signature"], challenge.env
    rng = random.Random("phase4-lever")
    ids = sorted(challenge.hitters)
    rows = []
    for _ in range(300):
        lineup = rng.sample(ids, a.LINEUP_SIZE)
        batters = [challenge.models[p] for p in lineup]
        rows.append((
            a.lineup_runs([a._probs_vector(b, challenge.avg_pitcher, env) for b in batters])["total"],  # raw quality
            a.lineup_runs([a._probs_vector(b, model, env) for b in batters])["total"],  # score vs. the ace
            np.mean([a.group_woba(challenge.models[p], challenge.avg_pitcher, env, sig)
                     - a.group_woba(challenge._neutral(p, sig), challenge.avg_pitcher, env, sig) for p in lineup]),
        ))
    flips = sum(
        1 for x, y in itertools.combinations(rows, 2)
        for better, worse in ((x, y), (y, x))
        if better[0] > worse[0] and better[1] < worse[1] and worse[2] > better[2]
    )
    pairs = len(rows) * (len(rows) - 1) // 2
    assert flips > 0, "A lineup that handles the signature pitch never beats a better-overall lineup"
    print(f"vs. {ace['name']} ({GROUP_NAMES[sig]}): {flips} of {pairs} lineup pairs ({flips / pairs:.1%}) - the lineup "
          f"with better raw quality scores less because the other handles the {GROUP_NAMES[sig]} better.")


if __name__ == "__main__":
    check_data()
    challenge = a.AceChallenge()
    check_kershaw(challenge)
    check_aces(challenge)
    check_scoring(challenge)
    check_lever(challenge)
    print("\nPhase 4 (Daily Mode Theme C) check passed.")
