"""
Shared stat engine, frozen to data/processed/ so Classic Mode and Daily Mode
both draw from the same computed stats instead of recomputing them:
season-level wOBA/FIP/OPS+/ERA+ (Classic) and era-adjusted career rates
(Daily).
"""

from warball import careers, data
from warball.batting import compute_batting_stats
from warball.data import PROCESSED_DIR
from warball.pitching import compute_pitching_stats


def build():
    batting = data.load_batting()
    pitching = data.load_pitching()
    fielding = data.load_fielding()
    teams = data.load_teams()

    batting_stats = compute_batting_stats(batting, fielding, teams)
    pitching_stats = compute_pitching_stats(pitching, teams)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    batting_stats.to_csv(PROCESSED_DIR / "batting_stats.csv", index=False)
    pitching_stats.to_csv(PROCESSED_DIR / "pitching_stats.csv", index=False)
    careers.build(batting_stats, pitching_stats)

    return batting_stats, pitching_stats


if __name__ == "__main__":
    b, p = build()
    print(f"Wrote {len(b)} batting player-team-seasons to {PROCESSED_DIR / 'batting_stats.csv'}")
    print(f"Wrote {len(p)} pitching player-team-seasons to {PROCESSED_DIR / 'pitching_stats.csv'}")
    print(f"Wrote career rates to {careers.BATTERS_FILE.name} and {careers.PITCHERS_FILE.name}")
