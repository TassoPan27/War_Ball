"""
Badge sanity check (docs: player-badges-spec.md, section 8).

  - well-known seasons earn the badge they're famous for
  - no badge from a season whose data can't support it
  - how often each badge is awarded, and how badged each decade's cards are
    (balance-testing input for BADGE_PERCENTILE)

Usage:
    python -m warball.pipeline      # batting stats now carry SB, CS, and missing-data flags
    python scripts/badges_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warball.badges import BADGE_PERCENTILE
from warball.draft import DraftPool

# (playerID, year, team, badge) - famous seasons for each badge
EXPECTED = [
    ("bondsba01", 2001, "SFN", "Slugger"),
    ("bondsba01", 2004, "SFN", "Table-Setter"),
    ("gwynnto01", 1995, "SDN", "Bat-to-Ball"),
    ("webbea01", 1931, "BOS", "Gap Power"),
    ("henderi01", 1988, "NYA", "Base Thief"),
    ("ripkeca01", 1990, "BAL", "Iron Man"),
    ("martipe02", 1999, "BOS", "Strikeout Artist"),
    ("maddugr01", 1997, "ATL", "Control Specialist"),
    ("maddugr01", 1994, "ATL", "Homer Suppressor"),
    ("roberro01", 1953, "PHI", "Workhorse"),
    ("riverma01", 2008, "NYA", "Bullpen Weapon"),
]


def names(badges) -> set:
    return {b["name"] for b in badges}


def check_famous(pool: DraftPool) -> list[str]:
    print("=== Famous seasons ===")
    failures = []
    seasons = {"h": pool.hitter_seasons, "p": pool.pitcher_seasons}
    for pid, year, team, badge in EXPECTED:
        rows = [df[(df["playerID"] == pid) & (df["yearID"] == year) & (df["teamID"] == team)] for df in seasons.values()]
        row = next((r.iloc[0] for r in rows if not r.empty), None)
        if row is None:
            failures.append(f"{pid} {year} {team}: no draft-qualified season")
            continue
        earned = names(row["badges"])
        ok = badge in earned
        print(f"  {'ok ' if ok else 'MISS'} {row['name']} {year} {team}: {badge} | earned: {', '.join(sorted(earned)) or 'none'}")
        if not ok:
            failures.append(f"{row['name']} {year} should earn {badge}")
    return failures


def check_data_gates(pool: DraftPool) -> list[str]:
    print("\n=== Data-era gates ===")
    h, p = pool.hitter_seasons, pool.pitcher_seasons
    failures = []
    bad_k = h[h["SO_missing"] & h["badges"].map(lambda b: "Bat-to-Ball" in names(b))]
    bad_sb = h[h["CS_missing"] & h["badges"].map(lambda b: "Base Thief" in names(b))]
    bad_gb = p[p["badges"].map(lambda b: "Groundball Machine" in names(b))]
    for label, bad in (("Bat-to-Ball without recorded strikeouts", bad_k), ("Base Thief without recorded caught stealing", bad_sb),
                       ("Groundball Machine awarded at all", bad_gb)):
        print(f"  {label}: {len(bad)}")
        if len(bad):
            failures.append(label)
    reliever_only = p[p["badges"].map(lambda b: "Bullpen Weapon" in names(b)) & (p["GS"] >= 0.5 * p["G"])]
    print(f"  Bullpen Weapon on a starter's season: {len(reliever_only)}")
    if len(reliever_only):
        failures.append("Bullpen Weapon on a starter")
    return failures


def report_balance(pool: DraftPool):
    print(f"\n=== Balance (BADGE_PERCENTILE = {BADGE_PERCENTILE:.0%}) ===")
    for label, df in (("Hitter", pool.hitter_seasons), ("Pitcher", pool.pitcher_seasons)):
        counts = df["badges"].explode().dropna().map(lambda b: b["name"]).value_counts()
        print(f"{label} seasons: {len(df):,}")
        for badge, n in counts.items():
            print(f"  {badge:<20} {n:>6,}  ({n / len(df):.1%} of seasons)")
    print("\nDraft cards with at least one badge, by decade:")
    for label, cards in (("hitters", pool.hitters), ("pitchers", pool.pitchers)):
        share = cards["badges"].map(bool).groupby(cards["yearID"] // 10 * 10).mean()
        print(f"  {label}: " + "  ".join(f"{d}s {s:.0%}" for d, s in share.items()))


if __name__ == "__main__":
    pool = DraftPool()
    failures = check_famous(pool) + check_data_gates(pool)
    report_balance(pool)
    if failures:
        print("\nFAILED:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("\nBadge check passed.")
