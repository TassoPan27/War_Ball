"""
Plate-appearance matchup engine (log5 / odds-ratio) for Daily Mode.

Every rate here lives in one reference environment (see careers.py), so a
matchup never has to know which eras the two players came from.

A plate appearance resolves in two steps, split along what the data supports
(and DIPS theory):

1. Batter vs. pitcher: log5 on the four buckets both sides have real data
   for: K, BB (walks plus HBP, counted the same way on both sides), HR, and
   BIP (ball in play). This is where the pitcher matters.
2. A ball in play falls for a hit at the batter's own BABIP (league average
   if he has none), and a hit's type follows his career 1B:2B:3B mix.
   Pitchers don't meaningfully control what a ball in play becomes (DIPS),
   and Lahman has no doubles/triples allowed for pitchers anyway. Hitters
   do: a Tony Gwynn's .338 average came from where his balls in play went,
   not just from rarely striking out.
"""

from dataclasses import dataclass

BUCKETS = ("K", "BB", "HR", "BIP")
HIT_TYPES = ("1B", "2B", "3B")
OUTCOMES = ("K", "BB", "HR", "1B", "2B", "3B", "OUT")  # OUT = ball in play turned into an out


def odds(p):
    return p / (1 - p)


def from_odds(o):
    return o / (1 + o)


@dataclass(frozen=True)
class Environment:
    rates: dict  # BUCKETS -> league-average rate per PA
    babip: float  # share of balls in play that fall for hits
    hit_mix: dict  # HIT_TYPES -> league-average share of non-HR hits


@dataclass(frozen=True)
class Batter:
    rates: dict  # BUCKETS -> rate per PA, already in the reference environment
    hit_mix: dict  # HIT_TYPES -> share of his non-HR hits
    babip: float | None = None  # share of his balls in play that fall for hits; None = league average


@dataclass(frozen=True)
class Pitcher:
    rates: dict  # BUCKETS -> rate per batter faced, already in the reference environment


def average_batter(env: Environment) -> Batter:
    return Batter(dict(env.rates), dict(env.hit_mix), env.babip)


def average_pitcher(env: Environment) -> Pitcher:
    return Pitcher(dict(env.rates))


def log5(batter_rates: dict, pitcher_rates: dict, league_rates: dict) -> dict:
    """Bucket probabilities for one plate appearance, renormalized to sum to 1.

    odds(o) = odds(batter_o) * odds(pitcher_o) / odds(league_o) for each bucket.
    The per-bucket formula doesn't keep the buckets summing to 1 on its own.
    """
    raw = {b: from_odds(odds(batter_rates[b]) * odds(pitcher_rates[b]) / odds(league_rates[b])) for b in BUCKETS}
    total = sum(raw.values())
    return {b: p / total for b, p in raw.items()}


def outcome_probs(batter: Batter, pitcher: Pitcher, env: Environment) -> dict:
    """Probabilities of every OUTCOME for one plate appearance."""
    p = log5(batter.rates, pitcher.rates, env.rates)
    babip = env.babip if batter.babip is None else batter.babip
    hits = p["BIP"] * babip
    return {
        "K": p["K"],
        "BB": p["BB"],
        "HR": p["HR"],
        **{t: hits * batter.hit_mix[t] for t in HIT_TYPES},
        "OUT": p["BIP"] * (1 - babip),
    }
