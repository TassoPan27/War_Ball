"""Property tests for the Theme C pitch-type matchup model (arsenal.py)."""

import math

import pytest

from warball import arsenal
from warball.arsenal import GROUPS, OUTCOMES

# League counts on plate appearances ending on each pitch group (rough 2015-2024 shapes).
LEAGUE = {
    "FB": {"PA": 50000, "K": 8500, "BB": 5500, "HBP": 600, "HR": 1700, "1B": 8200, "2B": 2600, "3B": 250, "OUT": 22650},
    "SL": {"PA": 20000, "K": 6000, "BB": 1400, "HBP": 250, "HR": 520, "1B": 2600, "2B": 800, "3B": 70, "OUT": 8360},
    "CU": {"PA": 10000, "K": 3000, "BB": 800, "HBP": 120, "HR": 260, "1B": 1300, "2B": 420, "3B": 40, "OUT": 4060},
    "CH": {"PA": 15000, "K": 3600, "BB": 900, "HBP": 100, "HR": 450, "1B": 2300, "2B": 700, "3B": 60, "OUT": 6890},
}
ENV = arsenal.league_environment(LEAGUE)


def scaled(counts: dict, factor: float) -> dict:
    return {k: round(v * factor) for k, v in counts.items()}


def test_average_vs_average_reproduces_the_league():
    probs = arsenal.outcome_probs(arsenal.average_batter(ENV), arsenal.average_pitcher(ENV), ENV)
    total = {k: sum(LEAGUE[g][k] for g in GROUPS) for k in LEAGUE["FB"]}
    assert math.isclose(sum(probs.values()), 1.0)
    assert probs["K"] == pytest.approx(total["K"] / total["PA"])
    assert probs["BB"] == pytest.approx((total["BB"] + total["HBP"]) / total["PA"])
    assert probs["HR"] == pytest.approx(total["HR"] / total["PA"])
    for t in ("1B", "2B", "3B", "OUT"):
        assert probs[t] == pytest.approx(total[t] / total["PA"])


def test_no_data_means_league_average_and_a_group_with_no_data_means_the_prior():
    nobody = arsenal.fit_batter({}, ENV)
    assert nobody.overall.rates == pytest.approx(ENV.overall.rates)
    assert nobody.overall.babip == pytest.approx(ENV.overall.babip)

    only_fastballs = arsenal.fit_batter({"FB": scaled(LEAGUE["FB"], 0.02)}, ENV)
    prior = arsenal.group_prior(only_fastballs.overall, ENV, "CU")
    assert only_fastballs.by_group["CU"].rates == pytest.approx(prior.rates)
    assert only_fastballs.by_group["CU"].babip == pytest.approx(prior.babip)


def test_curveball_crusher_gains_most_against_a_curveball_ace():
    ordinary = {g: scaled(LEAGUE[g], 0.03) for g in GROUPS}
    crusher = {**ordinary, "CU": {**ordinary["CU"], "K": 40, "HR": 25, "2B": 25, "OUT": 70}}
    ordinary_b, crusher_b = arsenal.fit_batter(ordinary, ENV), arsenal.fit_batter(crusher, ENV)

    curve_ace = arsenal.fit_pitcher({**{g: scaled(LEAGUE[g], 0.1) for g in GROUPS}, "CU": scaled(LEAGUE["CU"], 0.6)}, ENV)
    no_curve = arsenal.fit_pitcher({g: scaled(LEAGUE[g], 0.1) for g in ("FB", "SL", "CH")}, ENV)
    assert curve_ace.usage["CU"] > 0.3 and no_curve.usage["CU"] == 0

    gain = lambda p: arsenal.woba(arsenal.outcome_probs(crusher_b, p, ENV)) - arsenal.woba(arsenal.outcome_probs(ordinary_b, p, ENV))
    assert gain(curve_ace) > gain(no_curve) > 0


def test_probabilities_are_valid_for_fitted_players():
    b = arsenal.fit_batter({g: scaled(LEAGUE[g], 0.04) for g in GROUPS}, ENV)
    p = arsenal.fit_pitcher({g: scaled(LEAGUE[g], 0.08) for g in GROUPS}, ENV)
    probs = arsenal.outcome_probs(b, p, ENV)
    assert set(probs) == set(OUTCOMES)
    assert all(0 <= v <= 1 for v in probs.values())
    assert math.isclose(sum(probs.values()), 1.0)


def test_json_round_trips():
    b = arsenal.fit_batter({g: scaled(LEAGUE[g], 0.04) for g in GROUPS}, ENV)
    p = arsenal.fit_pitcher({g: scaled(LEAGUE[g], 0.08) for g in GROUPS}, ENV)
    assert arsenal.env_from_json(arsenal.env_to_json(ENV)) == ENV
    assert arsenal.batter_from_json(arsenal.batter_to_json(b)) == b
    assert arsenal.pitcher_from_json(arsenal.pitcher_to_json(p)) == p
