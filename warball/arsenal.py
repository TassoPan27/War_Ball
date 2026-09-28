"""
Pitch-type matchup model for Daily Mode Theme C (Great Pitchers).

Everything here lives in one environment, Statcast-era MLB (2015-2024; see
statcast.py), so no era adjustment is needed. A plate appearance against an
ace is split by the pitch group it ends on:

    P(outcome) = sum over groups g of  usage_ace(g) x P_g(outcome)

where usage_ace(g) is the share of the ace's plate appearances that end on
a pitch from group g, and P_g is the ordinary log5 matchup (matchup.py) of
the batter's rates vs. that group, the ace's rates with that group, and the
league's rates on that group. So a hitter who handles curveballs gains the
most against an ace whose plate appearances often end on one.

Samples against one pitch group are small (a regular sees a few hundred
plate appearances end on curveballs in a decade), so each hitter's group
rates are shrunk toward a *prior built from his own overall skill*: his
overall odds ratio applied to the league's rates on that group. A hitter's
edge against curveballs is therefore only what the data shows beyond how
good he is in general, which is exactly the counter-lever the theme is about.

Known simplifications: handedness is ignored (a hitter's rates vs. a group
mix left- and right-handed pitchers), and pitch groups are coarse (see
GROUPS).
"""

from dataclasses import dataclass

from warball import matchup
from warball.careers import BABIP_SHRINK, BATTER_SHRINK, HIT_MIX_SHRINK, PITCHER_SHRINK  # career-level, toward league
from warball.constants import WOBA_WEIGHTS
from warball.matchup import BUCKETS, HIT_TYPES, OUTCOMES, Batter, Environment, Pitcher, from_odds, odds

# Statcast pitch_type codes -> pitch groups. Rare types (knuckleball, eephus,
# pitch-outs) have no group, and plate appearances ending on them are dropped.
GROUPS = ("FB", "SL", "CU", "CH")
GROUP_NAMES = {"FB": "fastball", "SL": "slider", "CU": "curveball", "CH": "changeup"}
PITCH_GROUP = {
    "FF": "FB", "FA": "FB", "SI": "FB", "FT": "FB", "FC": "FB",
    "SL": "SL", "ST": "SL", "SV": "SL",
    "CU": "CU", "KC": "CU", "CS": "CU",
    "CH": "CH", "FS": "CH", "FO": "CH", "SC": "CH",
}

COUNT_COLUMNS = ("PA", "K", "BB", "HBP", "HR", "1B", "2B", "3B", "OUT")

# Shrinkage toward a player's overall rates, in plate appearances (or balls in
# play, for BABIP) ending on that pitch group. Lighter than the career-level
# shrinkage in careers.py because the prior here already carries the player's
# own overall skill.
GROUP_SHRINK = {"K": 60, "BB": 100, "HR": 150, "BIP": 60}
GROUP_BABIP_SHRINK = 400


@dataclass(frozen=True)
class ArsenalEnv:
    overall: Environment
    by_group: dict  # group -> Environment on plate appearances ending on that group
    usage: dict  # group -> league share of plate appearances ending on that group


@dataclass(frozen=True)
class ArsenalBatter:
    overall: Batter
    by_group: dict  # group -> Batter


@dataclass(frozen=True)
class ArsenalPitcher:
    usage: dict  # group -> share of his plate appearances ending on that group
    by_group: dict  # group -> Pitcher


def outcome_probs(batter: ArsenalBatter, pitcher: ArsenalPitcher, env: ArsenalEnv) -> dict:
    """Probabilities of every OUTCOME for one plate appearance, mixed over the pitcher's pitch groups."""
    total = dict.fromkeys(OUTCOMES, 0.0)
    for g, share in pitcher.usage.items():
        if share <= 0:
            continue
        probs = matchup.outcome_probs(batter.by_group[g], pitcher.by_group[g], env.by_group[g])
        for o in OUTCOMES:
            total[o] += share * probs[o]
    return total


def woba(probs: dict) -> float:
    """Linear-weights wOBA of an outcome distribution (walks and HBP share the unintentional-walk weight)."""
    w = WOBA_WEIGHTS
    return w["uBB"] * probs["BB"] + sum(w[t] * probs[t] for t in (*HIT_TYPES, "HR"))


def average_batter(env: ArsenalEnv) -> ArsenalBatter:
    return ArsenalBatter(matchup.average_batter(env.overall), {g: matchup.average_batter(env.by_group[g]) for g in GROUPS})


def average_pitcher(env: ArsenalEnv) -> ArsenalPitcher:
    return ArsenalPitcher(dict(env.usage), {g: matchup.average_pitcher(env.by_group[g]) for g in GROUPS})


# ---------- Fitting from counts ----------


def _normalize(rates: dict) -> dict:
    total = sum(rates.values())
    return {k: v / total for k, v in rates.items()}


def _bucket_counts(c: dict) -> dict:
    """Counts (see COUNT_COLUMNS) -> model buckets. HBP counts as a walk, as in careers.py."""
    return {
        "K": c["K"],
        "BB": c["BB"] + c["HBP"],
        "HR": c["HR"],
        "BIP": c["1B"] + c["2B"] + c["3B"] + c["OUT"],
    }


def _sum_counts(counts: list[dict]) -> dict:
    return {k: sum(c.get(k, 0) for c in counts) for k in COUNT_COLUMNS}


def environment(counts: dict) -> Environment:
    """League environment from summed counts."""
    buckets = _bucket_counts(counts)
    hits = counts["1B"] + counts["2B"] + counts["3B"]
    return Environment(
        rates={b: buckets[b] / counts["PA"] for b in BUCKETS},
        babip=hits / buckets["BIP"],
        hit_mix={t: counts[t] / hits for t in HIT_TYPES},
    )


def league_environment(by_group: dict) -> ArsenalEnv:
    """by_group: group -> league counts on plate appearances ending on that group."""
    total = _sum_counts(list(by_group.values()))
    return ArsenalEnv(
        overall=environment(total),
        by_group={g: environment(by_group[g]) for g in GROUPS},
        usage={g: by_group[g]["PA"] / total["PA"] for g in GROUPS},
    )


def _shrunk_rates(counts: dict, prior: dict, shrink: dict) -> dict:
    buckets = _bucket_counts(counts)
    pa = counts["PA"]
    return _normalize({b: (buckets[b] + prior[b] * shrink[b]) / (pa + shrink[b]) for b in BUCKETS})


def _shrunk_babip(counts: dict, prior: float, shrink: float) -> float:
    bip = _bucket_counts(counts)["BIP"]
    hits = counts["1B"] + counts["2B"] + counts["3B"]
    return (hits + prior * shrink) / (bip + shrink)


def translate(rates: dict, source: dict, target: dict) -> dict:
    """A player's rates in one environment carried to another by the odds-ratio method."""
    return _normalize({b: from_odds(odds(rates[b]) * odds(target[b]) / odds(source[b])) for b in rates})


def translate_rate(rate: float, source: float, target: float) -> float:
    return from_odds(odds(rate) * odds(target) / odds(source))


def group_prior(overall: Batter, env: ArsenalEnv, g: str) -> Batter:
    """What a batter's overall skill alone predicts for plate appearances ending on group g."""
    babip = env.overall.babip if overall.babip is None else overall.babip
    return Batter(
        translate(overall.rates, env.overall.rates, env.by_group[g].rates),
        overall.hit_mix,
        translate_rate(babip, env.overall.babip, env.by_group[g].babip),
    )


def fit_batter(by_group: dict, env: ArsenalEnv) -> ArsenalBatter:
    """by_group: group -> this batter's counts on plate appearances ending on that group."""
    total = _sum_counts([by_group.get(g, {}) for g in GROUPS])
    hits = total["1B"] + total["2B"] + total["3B"]
    overall = Batter(
        _shrunk_rates(total, env.overall.rates, BATTER_SHRINK),
        _normalize({t: (total[t] + env.overall.hit_mix[t] * HIT_MIX_SHRINK) / (hits + HIT_MIX_SHRINK) for t in HIT_TYPES}),
        _shrunk_babip(total, env.overall.babip, BABIP_SHRINK),
    )
    groups = {}
    for g in GROUPS:
        prior = group_prior(overall, env, g)
        counts = _sum_counts([by_group.get(g, {})])
        groups[g] = Batter(
            _shrunk_rates(counts, prior.rates, GROUP_SHRINK),
            overall.hit_mix,
            _shrunk_babip(counts, prior.babip, GROUP_BABIP_SHRINK),
        )
    return ArsenalBatter(overall, groups)


def fit_pitcher(by_group: dict, env: ArsenalEnv) -> ArsenalPitcher:
    total = _sum_counts([by_group.get(g, {}) for g in GROUPS])
    overall = _shrunk_rates(total, env.overall.rates, PITCHER_SHRINK)
    groups = {}
    for g in GROUPS:
        prior = translate(overall, env.overall.rates, env.by_group[g].rates)
        groups[g] = Pitcher(_shrunk_rates(_sum_counts([by_group.get(g, {})]), prior, GROUP_SHRINK))
    usage = {g: by_group.get(g, {}).get("PA", 0) / total["PA"] for g in GROUPS}
    return ArsenalPitcher(usage, groups)


# ---------- JSON ----------


def env_to_json(env: ArsenalEnv) -> dict:
    as_dict = lambda e: {"rates": e.rates, "babip": e.babip, "hit_mix": e.hit_mix}
    return {"overall": as_dict(env.overall), "by_group": {g: as_dict(e) for g, e in env.by_group.items()}, "usage": env.usage}


def env_from_json(d: dict) -> ArsenalEnv:
    return ArsenalEnv(
        Environment(**d["overall"]), {g: Environment(**e) for g, e in d["by_group"].items()}, d["usage"]
    )


def batter_to_json(b: ArsenalBatter) -> dict:
    as_dict = lambda x: {"rates": x.rates, "hit_mix": x.hit_mix, "babip": x.babip}
    return {"overall": as_dict(b.overall), "by_group": {g: as_dict(x) for g, x in b.by_group.items()}}


def batter_from_json(d: dict) -> ArsenalBatter:
    return ArsenalBatter(Batter(**d["overall"]), {g: Batter(**x) for g, x in d["by_group"].items()})


def pitcher_to_json(p: ArsenalPitcher) -> dict:
    return {"usage": p.usage, "by_group": {g: x.rates for g, x in p.by_group.items()}}


def pitcher_from_json(d: dict) -> ArsenalPitcher:
    return ArsenalPitcher(d["usage"], {g: Pitcher(r) for g, r in d["by_group"].items()})
