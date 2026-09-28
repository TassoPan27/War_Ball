# WARBall

An era-spanning MLB draft and simulation game where every rating is a real, visible sabermetric stat — not a hidden multiplier.

## Modes

**Classic Mode — Era Draft.** Each pick spins a random franchise and decade (e.g. *1990s Atlanta Braves*); you draft one player's peak season with that team in that decade into an eligible roster slot. Fill a 9-man lineup, 5-man rotation, and 3-man bullpen, draft a real manager as your coach, then simulate a 162-game season. The goal: go 162-0.

**Daily Mode — Beat the Legends.** A daily puzzle (same for everyone, seeded by UTC date). Today's theme is Power Hitters: draft three elite starters to face a lineup of all-time sluggers. Every plate appearance is a log5 matchup of era-adjusted career rates, and your score is expected runs allowed versus a calibrated par.

## The math

- **Hitters:** wOBA, wRAA, and an approximate WAR (batting runs + positional adjustment + replacement level); era- and park-adjusted OPS+.
- **Pitchers:** FIP, FIP−, park- and era-adjusted ERA+, and FIP-based runs saved.
- **Era fairness:** every player is measured against their own year and league. Daily Mode converts careers to a modern (2015–2024) environment with the odds-ratio method, shrinking small samples toward average.
- **Season sim:** lineup runs above average and staff runs saved feed the Pythagorean win formula (exponent 1.83).
- **Matchup sim:** log5 on K / BB / HR / ball in play, then an exact base-out state machine turns outcomes into expected runs.
- Short seasons (2020, the 1870s, the Negro Leagues) are kept by scaling playing-time thresholds to team games played.

## Getting started

Requires Python 3.11+.

```bash
pip install -r requirements.txt
```

1. Download the [Lahman Baseball Database](https://www.seanlahman.com/) CSVs into `data/lahman/` (`Batting.csv`, `Pitching.csv`, `Fielding.csv`, `Teams.csv`, `People.csv`, `Managers.csv`, `FieldingOF.csv`, `FieldingOFsplit.csv`, …).
2. Build the stat engine and calibrate Daily Mode par:
   ```bash
   python -m warball.pipeline
   python -m warball.daily
   ```
3. Run the game and open http://127.0.0.1:8000 (Classic) or `/daily.html` (Daily):
   ```bash
   python -m warball.server
   ```

There's also a terminal version of the Classic draft: `python scripts/cli_draft.py`.

## Checks and tests

```bash
python -m pytest tests
python scripts/phase1_check.py   # stat engine vs. known career numbers
python scripts/phase2_check.py   # Classic draft + season sim
python scripts/phase3_check.py   # Daily Mode: par, spread, theme lever
```

## Known simplifications

- The base-out engine uses simple advancement rules (no sac flies, double plays, or extra bases), undercounting runs slightly — equally for every staff.
- Odds-ratio era adjustment amplifies sluggers from very low-HR eras (Babe Ruth adjusts to a 16.9% HR rate); power Legends also need a 4% raw HR rate.
- Negro League hitters are excluded from Daily Mode lineups because their strikeouts weren't recorded.

## Roadmap

Contact Hitters and Great Pitchers (Statcast) themes, a daily leaderboard, era bonuses/penalties, player "badges," and teammate/duo bonuses. See `warball-roadmap.md` and `warball-mlb-concept.md`.
