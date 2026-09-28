# WARBall — Build Roadmap

Two modes, and Daily Mode itself has three themes with three different data needs. Classic Mode and Daily Mode Themes A/B run entirely on season-level Lahman stats — no special data pull needed. Theme C (Great Pitchers) needs Statcast pitch-type data, which only exists from 2015 onward. The phases below sequence so everything except Theme C can ship first, since it's both the most data-intensive and the most scope-limited piece.

---

## Phase 0 — Validate Before You Build

- [ ] Pull a small test batch from the Lahman database (a handful of players/seasons) and confirm the fields you need (batting, pitching, fielding — including HR, K%, BB%) are all there and clean
- [ ] Pull a small test batch from Baseball Savant's public Statcast data for one modern pitcher (Kershaw is the obvious test case) and confirm you can get pitch-type-level batter performance (e.g. batter wOBA vs. curveballs specifically) — this is the riskiest technical assumption in the whole project and is isolated entirely to Theme C, worth confirming early so you know if that theme is realistic on your timeline
- [ ] Sanity-check the Kershaw pull against what's publicly known about his pitch mix and results — if the data doesn't clearly show the curveball as his dominant weapon, something's off in how you're pulling or aggregating it

## Phase 1 — Core Stat Pipeline (shared by both modes)

- [ ] Compute wOBA and an approximate WAR (batting runs above average + positional adjustment + replacement baseline) for batters from Lahman
- [ ] Compute FIP for pitchers from Lahman
- [ ] Compute era-adjusted OPS+ and ERA+ for all players — this is your era-fairness mechanism, do it once and reuse everywhere
- [ ] Freeze this as the shared engine both modes will draw from

## Phase 2 — Classic Mode: Draft + Season Simulation

- [ ] Draft UI: spin a franchise/era combination, position eligibility rules, real positional-adjustment penalties (not an arbitrary flat percentage)
- [ ] Pitching staff sub-draft: rotation + bullpen slots, scored the same transparent way as batters
- [ ] Season simulation via the Pythagorean win-expectation formula, fed by team wOBA/FIP
- [ ] Season summary / scorecard display showing the math, not just a final record

This phase is a complete, shippable v1 on its own — worth treating as a real milestone before starting Phase 3.

## Phase 3 — Daily Mode Themes A & B (Power Hitters / Contact Hitters)

Both themes run on Lahman data alone, so build them together.

- [ ] Compute ISO (SLG − AVG) and HR rate for batters — this is how a Legends lineup qualifies as a "Power Hitters" team, any era
- [ ] Compute strikeout rate and contact rate for batters — this is how a Legends lineup qualifies as a "Contact Hitters" team, any era
- [ ] Compute HR/9 allowed for pitchers — the counter-lever for Theme A
- [ ] Compute BB% (walk rate) for pitchers — the counter-lever for Theme B
- [ ] Curate 3–5 Legends lineups for each theme (power-hitter-heavy and contact-hitter-heavy rosters) from real players ranking highly on the relevant stat
- [ ] Deterministic UTC-date picker selecting which theme, and which specific Legends lineup within it, is live each day
- [ ] Small pitching-staff draft UI for these two themes — a starter plus a couple of relievers is enough to keep it fast
- [ ] Matchup simulation combining raw pitcher quality with the theme-specific counter-lever (HR/9 for Theme A, BB% for Theme B)
- [ ] Score display that separates raw pitcher quality from the theme-specific matchup edge, so the player can see *why* they did well or badly

This phase is a complete, shippable Daily Mode on its own — Theme C in Phase 4 is a scoped addition, not a prerequisite.

## Phase 4 — Daily Mode Theme C (Great Pitchers)

- [ ] Pull Statcast pitch-type data for a curated set of modern (2015+) aces — Kershaw and a handful of others with well-known signature pitches
- [ ] For each, confirm their dominant/signature pitch from the real data (whiff rate, usage rate, or run value by pitch type)
- [ ] Pull batter performance by pitch type (e.g. wOBA vs. curveballs) for a modern hitter pool, to power the counter-draft
- [ ] Full 9-hitter lineup draft UI for this theme, distinct from the smaller staff draft in Themes A/B
- [ ] Matchup simulation and score breakdown showing how much of the result came from the batters' specific pitch-type performance vs. their general quality

## Phase 5 — Beat the Field (Leaderboard Backend)

- [ ] Minimal backend + database for daily submissions (score, timestamp, anonymous device/session token) — same pattern as the Champions League project's leaderboard; if you're building both, this infrastructure can likely be shared rather than built twice
- [ ] Block duplicate same-day submissions per token
- [ ] Percentile ranking against today's other submissions
- [ ] Local streak tracking, midnight UTC reset

## Phase 6 — Weekly Extension (optional)

- [ ] A longer-form weekly version of Classic Mode — full season, bigger roster stakes — paralleling the weekly bracket mode in the Champions League project, for consistency across both games if you ship both

## Phase 7 — Portfolio Packaging

- [ ] Methodology README covering both modes — the era-adjustment story for Classic Mode, and the three-theme matchup story for Daily Mode (power suppression, command, and pitch-type-specific hitting), including an honest note on why Theme C is scoped to the Statcast era
- [ ] Deploy a live demo
- [ ] Short walkthrough recording for your resume/portfolio site
