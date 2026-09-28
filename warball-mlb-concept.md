# WARBall — Era-Spanning MLB Draft & Simulation Game
### Concept Document (v3 — themed matchup puzzles)

**Working title:** WARBall
**One-line pitch:** Draft an all-time MLB roster and simulate its season, or take on a themed legendary team in a daily matchup puzzle — every rating is a real, visible sabermetric stat, not a hidden multiplier.

---

## Two Modes, Read First

1. **Classic Mode — Era Draft & Season.** The deeper, open-ended mode: draft a full roster across baseball history, simulate a season.
2. **Daily Mode — Beat the Legends.** A themed daily puzzle. Each day's Legends team is built around a specific identity — great power, great contact, or a single dominant ace — and your draft flips depending on the theme. The skill is reading *what* makes today's Legends team dangerous and drafting specifically to counter it, not just picking the highest-rated players available.

## Mode 1: Classic Draft & Season (unchanged)

- Draft a 9-spot batting order plus a pitching staff (rotation + bullpen), across any era.
- Scoring uses real, visible sabermetrics — wOBA and an approximate WAR for batters, FIP for pitchers, era-adjusted OPS+/ERA+ so a player's rating already accounts for their era.
- Real positional-adjustment values (from WAR methodology) instead of an arbitrary flat penalty.
- Season simulation via the Pythagorean win-expectation formula.

## Mode 2: Daily — "Beat the Legends" (three themes)

Each day's challenge rotates through a theme (deterministic UTC-date seed, same convention as before). The theme changes two things at once: **who you draft**, and **what specific weakness you're drafting against**.

| Theme | Legends team is... | You draft... | The counter-lever | Data needed |
|---|---|---|---|---|
| **Power Hitters** | Legendary sluggers (high ISO/HR rate) | Pitchers | Home-run/power suppression | Lahman — any era |
| **Contact Hitters** | Legendary high-contact, low-strikeout bats | Pitchers | Command/control | Lahman — any era |
| **Great Pitchers** | One dominant legendary ace | Hitters | Performance vs. his signature pitch | Statcast — 2015+ only |

### Theme A: Power Hitters

Today's Legends lineup is identified by real, simple stats — high isolated power (SLG minus AVG) and/or home-run rate, computable from standard stats for any era of baseball history. You draft a pitching staff. The counter-lever is **home runs allowed per 9 innings** — a pitcher who's historically stingy with the long ball blunts a power-heavy lineup's whole advantage, and this is a real, always-available stat, not something invented for the game. (For pitchers from roughly 2002 onward, you could layer in ground-ball rate as a sharper version of the same idea — power hitters do more damage on balls in the air — but HR/9 alone is enough to make this theme playable across all of baseball history.)

### Theme B: Contact Hitters

Today's Legends lineup is identified by a low strikeout rate and high contact rate — again, computable from standard stats for any era. You draft a pitching staff. The counter-lever here is **walk rate (BB%)** — worth being upfront that this is a real but softer design judgment than Theme A's, not an established law: a contact-heavy lineup is hard to beat with swing-and-miss stuff since they make contact regardless of how nasty your pitch is, so command — not eliminating contact, but limiting free baserunners around it — is the more defensible lever than trying to out-strikeout hitters who are specifically good at not striking out.

### Theme C: Great Pitchers

Today's Legends team is a single dominant historical ace — your example: **Clayton Kershaw, whose signature weapon is his curveball.** You draft a full batting lineup. The counter-lever is real batter performance *specifically against that pitch type* — e.g. a hitter's wOBA or whiff rate against curveballs, not their overall numbers. A team of otherwise-ordinary hitters who happen to be genuinely good against curveballs, historically, is a real, defensible edge against Kershaw specifically — even though it wouldn't matter against a fastball-dominant ace.

**The real constraint worth knowing now:** pitch-type-specific batter data (performance broken out by curveball vs. fastball vs. slider, etc.) only exists in structured form from the Statcast era onward — roughly 2015 to today, via Baseball Savant's public data. There's no way to honestly compute "who historically hit Sandy Koufax's curveball well" the same way, because pitch-by-pitch tracking data simply doesn't exist for that era. That means **Theme C has to be scoped to modern legends** — Kershaw works great as an example precisely because he's a Statcast-era pitcher. If you want this theme to include older aces later, the honest options are either accepting it as a "Modern Legends" theme permanently, or building a separate, explicitly qualitative version for older pitchers (curated scouting-report facts, not real computed stats) — which I'd avoid, since it breaks the "real, visible math" principle that's the whole differentiator from a hidden-formula game like Era Ball.

## Data & Methodology

- **Classic Mode + Themes A & B:** Lahman Baseball Database — season-level batting/pitching stats, covers all of baseball history, no new dependency beyond what Classic Mode already needs.
- **Theme C:** Baseball Savant's public Statcast data — pitch-type breakdowns and batter performance by pitch type, available for the 2015-onward era. This is a genuinely separate data source from the rest of the project, worth scoping as its own pipeline step.
- **Sanity-check whichever lever you build** against a real, widely-known case before trusting it broadly — e.g. confirm Kershaw's curveball actually shows up as his dominant weapon in the Statcast data the way scouting reports say, before building the full theme on top of that assumption.

## Suggested Tech Stack

Unchanged from before — Python for the data/modeling pipeline, a lightweight front end consuming precomputed data. Theme C adds one more data-pull step (Baseball Savant) alongside the existing Lahman/Retrosheet pulls. Daily Mode's leaderboard needs the same lightweight backend-plus-database pattern as the Champions League project's "beat the field" system — that infrastructure could realistically be shared between the two if you build both.

## Why This Is a Strong Portfolio Piece

- Three themes, three distinct real sabermetric levers (power suppression, command, pitch-type-specific performance) — a much richer "here's what I actually modeled" story than one mechanic reused three times.
- Theme C's honest data-era constraint is itself a good talking point: it shows you understood the limits of the data rather than papering over them with a fake number.
- The overall "identify what makes today's opponent dangerous, then draft the specific counter" framing is a stronger, more replayable puzzle than "draft the best possible team," and it's a natural three-day rotation that keeps the daily habit from feeling repetitive.

## Open Decisions Before You Start Building

- Whether to launch with all three themes or start with just Theme A (Power Hitters) — it's the simplest to build (pure Lahman data, always-available HR/9 lever) and would validate the whole "themed daily puzzle" concept before you take on Theme C's Statcast pipeline.
- Whether Theme C stays a permanent "Modern Legends" theme or you eventually build the separate qualitative version for older aces.
- How many pitchers/hitters the player drafts per day in each theme — a single ace-vs-lineup framing (Theme C) suggests a full 9-hitter lineup, while Themes A/B could reasonably stay to a smaller staff (a starter plus a couple of relievers) to keep the daily mode fast.
