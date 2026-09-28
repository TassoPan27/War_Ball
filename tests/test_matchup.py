"""Property tests for the log5 matchup engine and the base-out run engine (spec section 5)."""

import math

import numpy as np
import pytest

from warball.matchup import BUCKETS, OUTCOMES, Batter, Environment, Pitcher, average_batter, average_pitcher, log5, outcome_probs
from warball.runs import _advance, _expected_runs_sequence, expected_runs

ENV = Environment(
    rates={"K": 0.22, "BB": 0.09, "HR": 0.03, "BIP": 0.66},
    babip=0.30,
    hit_mix={"1B": 0.75, "2B": 0.23, "3B": 0.02},
)
SLUGGER = Batter({"K": 0.25, "BB": 0.15, "HR": 0.08, "BIP": 0.52}, {"1B": 0.65, "2B": 0.31, "3B": 0.04})
ACE = Pitcher({"K": 0.33, "BB": 0.06, "HR": 0.02, "BIP": 0.59})
HR_PRONE = Pitcher({"K": 0.22, "BB": 0.09, "HR": 0.05, "BIP": 0.64})


def test_average_vs_average_returns_league_rates():
    p = log5(ENV.rates, ENV.rates, ENV.rates)
    for b in BUCKETS:
        assert p[b] == pytest.approx(ENV.rates[b])


def test_average_pitcher_leaves_batter_unchanged_and_vice_versa():
    assert log5(SLUGGER.rates, ENV.rates, ENV.rates) == pytest.approx(SLUGGER.rates)
    assert log5(ENV.rates, ACE.rates, ENV.rates) == pytest.approx(ACE.rates)


def test_better_pitcher_lowers_hr_and_worse_pitcher_raises_it():
    against_average = log5(SLUGGER.rates, ENV.rates, ENV.rates)["HR"]
    assert log5(SLUGGER.rates, ACE.rates, ENV.rates)["HR"] < against_average
    assert log5(SLUGGER.rates, HR_PRONE.rates, ENV.rates)["HR"] > against_average


@pytest.mark.parametrize("batter", [SLUGGER, average_batter(ENV)])
@pytest.mark.parametrize("pitcher", [ACE, HR_PRONE, average_pitcher(ENV)])
def test_outcomes_are_valid_probabilities_summing_to_one(batter, pitcher):
    probs = outcome_probs(batter, pitcher, ENV)
    assert set(probs) == set(OUTCOMES)
    assert all(0 <= p <= 1 for p in probs.values())
    assert math.isclose(sum(probs.values()), 1.0)


def test_extreme_inputs_still_renormalize():
    whiffer = Batter({"K": 0.45, "BB": 0.20, "HR": 0.12, "BIP": 0.23}, ENV.hit_mix)
    strikeout_king = Pitcher({"K": 0.45, "BB": 0.12, "HR": 0.05, "BIP": 0.38})
    assert math.isclose(sum(log5(whiffer.rates, strikeout_king.rates, ENV.rates).values()), 1.0)


@pytest.mark.parametrize(
    "outs, bases, outcome, expected",
    [
        (0, 0b000, "HR", (0, 0b000, 1)),
        (1, 0b111, "HR", (1, 0b000, 4)),
        (0, 0b111, "BB", (0, 0b111, 1)),  # walk with the bases loaded forces in a run
        (0, 0b100, "BB", (0, 0b101, 0)),  # runner on third holds on a walk
        (0, 0b101, "1B", (0, 0b011, 1)),  # single: third scores, first to second
        (0, 0b011, "2B", (0, 0b110, 1)),  # double: second scores, first to third
        (2, 0b111, "3B", (2, 0b100, 3)),
        (2, 0b011, "K", (3, 0b011, 0)),
    ],
)
def test_base_out_rules(outs, bases, outcome, expected):
    assert _advance(outs, bases, outcome) == expected


def test_certain_outcomes_give_exact_runs():
    one_hot = lambda o: np.array([1.0 if x == o else 0.0 for x in OUTCOMES])
    assert _expected_runs_sequence([one_hot("HR")] * 4).sum() == 4
    assert _expected_runs_sequence([one_hot("BB")] * 5).sum() == 2  # 4th and 5th walks force runs in
    # Three strikeouts end the inning, so the next walks start with empty bases again.
    assert _expected_runs_sequence([one_hot("BB")] * 3 + [one_hot("K")] * 3 + [one_hot("BB")] * 3).sum() == 0


def test_expected_runs_is_deterministic_and_order_invariant():
    lineup = [SLUGGER, average_batter(ENV)] * 4 + [SLUGGER]
    staff = [ACE, HR_PRONE, average_pitcher(ENV)]
    a = expected_runs(lineup, staff, ENV)["total"]
    assert a == expected_runs(lineup, staff, ENV)["total"]
    assert a == pytest.approx(expected_runs(lineup, list(reversed(staff)), ENV)["total"])


def test_better_staff_allows_fewer_runs():
    lineup = [SLUGGER] * 9
    aces = expected_runs(lineup, [ACE] * 3, ENV)["total"]
    average = expected_runs(lineup, [average_pitcher(ENV)] * 3, ENV)["total"]
    assert aces < average
