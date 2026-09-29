# WARBall

An era-spanning MLB draft and simulation game where every rating is a real, visible sabermetric stat — not a hidden multiplier.

## Modes

**Classic Mode — Era Draft.** Each pick spins a random franchise and decade (e.g. *1990s Atlanta Braves*); you draft one player's peak season with that team in that decade into an eligible roster slot. The draft runs in three screens: a 9-man lineup, then a 5-man rotation and 3-man bullpen, then a real manager as your coach. Don't like a spin? You get 3 re-spins for your roster and 3 for your coach. Then simulate a 162-game season. Cards are tiered bronze to diamond (season WAR / FIP−) and carry specialization badges (Slugger, Table-Setter, Bat-to-Ball, Gap Power, Base Thief, Iron Man; Strikeout Artist, Control Specialist, Homer Suppressor, Workhorse, Bullpen Weapon): each is a real stat in the top 10% of its year and league, and each is worth +3 runs in the season sim. The goal: go 162-0.

**Daily Mode — Beat the Legends.** A daily puzzle (same for everyone, seeded by UTC date) that alternates between two themes:

| Theme | You face | You draft | The counter-lever |
|---|---|---|---|
| **Power Hitters** | nine career sluggers (1893 on) | 3 elite starters | home-run suppression |
| **Great Pitchers** | one modern ace (2015–2024) | 9 modern hitters | handling his signature pitch |

Every plate appearance is a log5 matchup, and your score is expected runs (allowed, or scored against the ace) versus a calibrated par.

## The math

- **Hitters:** wOBA, wRAA, and an approximate WAR (batting runs + positional adjustment + replacement level); era- and park-adjusted OPS+.
- **Pitchers:** FIP, FIP−, park- and era-adjusted ERA+, and FIP-based runs saved.
- **Era fairness:** every player is measured against their own year and league. Daily Mode converts careers to a modern (2015–2024) environment with the odds-ratio method, shrinking small samples toward average.
- **Season sim:** lineup runs above average and staff runs saved feed the Pythagorean win formula (exponent 1.83).
- **Matchup sim:** log5 on K / BB / HR / ball in play; a ball in play falls for a hit at the batter's own era-adjusted, shrunk BABIP (pitchers don't control it). An exact base-out state machine turns outcomes into expected runs.
- **Great Pitchers (Statcast):** every plate appearance is split by the pitch group it ends on (fastball / slider / curveball / changeup), with a log5 matchup per group weighted by the ace's pitch mix. A hitter's rates against each group are shrunk toward what his overall skill predicts, so his edge against a curveball is only what the data shows beyond how good he is in general. Each ace's signature pitch is chosen from the data (the group where he beats the league by the most wOBA), not from scouting reports.
- Short seasons (2020, the 1870s, the Negro Leagues) are kept by scaling playing-time thresholds to team games played.

## Getting started

Requires Python 3.11+.

```bash
pip install -r requirements.txt
```

1. Download the [Lahman Baseball Database](https://www.seanlahman.com/) CSVs into `data/lahman/` (`Batting.csv`, `Pitching.csv`, `Fielding.csv`, `Teams.csv`, `People.csv`, `Managers.csv`, `FieldingOF.csv`, `FieldingOFsplit.csv`, …).
2. Build the stat engine and calibrate Daily Mode par (Power Hitters):
   ```bash
   python -m warball.pipeline
   python -m warball.daily
   ```
3. For Great Pitchers, pull 2015–2024 Statcast from Baseball Savant (resumable per season, roughly 10–30 minutes a season) and pick the aces:
   ```bash
   python -m warball.statcast
   python -m warball.aces
   ```
   The rotation skips any theme that isn't built yet.
4. Run the game and open http://127.0.0.1:8000 (Classic) or `/daily.html` (Daily). Add `?theme=power|aces` (and `&date=YYYY-MM-DD`) to preview another day's puzzle:
   ```bash
   python -m warball.server
   ```

There's also a terminal version of the Classic draft: `python scripts/cli_draft.py`.

## Checks and tests

```bash
python -m pytest tests
python scripts/phase1_check.py   # stat engine vs. known career numbers
python scripts/phase2_check.py   # Classic draft + season sim
python scripts/badges_check.py   # badges: famous seasons, data-era gates, balance
python scripts/phase3_check.py   # Daily Mode Power Hitters: Legends, par, spread, theme lever
python scripts/phase4_check.py   # Daily Mode Great Pitchers: Statcast coverage, Kershaw's curveball, par, lever
```

## Known simplifications

- The base-out engine uses simple advancement rules (no sac flies, double plays, or extra bases), undercounting runs slightly — equally for every staff.
- Odds-ratio era adjustment amplifies sluggers from very low-HR eras (Babe Ruth adjusts to a 16.9% HR rate); power Legends also need a 4% raw HR rate.
- Daily Mode Legends must have played most of their careers from 1893 on, when the pitching distance reached 60'6"; before that (underhand pitching until 1884, 50 feet) it was a different game.
- Negro League hitters are excluded from Daily Mode lineups because their strikeouts weren't recorded.
- Great Pitchers ignores handedness (a hitter's rates against a pitch group mix lefties and righties), uses four coarse pitch groups, and drops the rare plate appearances that end on a knuckleball, eephus, or other unclassified pitch.
- Par is calibrated against random entries from the whole pool, so on a day when the drafted-from pool is unusually strong, more than 30% of entries beat par.

## Roadmap

A daily leaderboard (Phase 5), era bonuses/penalties, player "badges," and teammate/duo bonuses. See `warball-roadmap.md` and `warball-mlb-concept.md`.
