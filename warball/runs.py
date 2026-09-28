"""
Turns plate-appearance outcome probabilities into runs with a simple
base-out state machine: 24 states (0-2 outs x 8 base configurations); a third
out ends the inning and clears the bases.

Advancement rules (deliberately simple, applied the same to everyone):
    K, OUT   batter out, runners hold (no sac flies, double plays, or
             runners moving up on outs)
    BB       batter to first; runners advance only when forced
    1B       batter to first; every runner advances one base
    2B       batter to second; every runner advances two bases
    3B       batter to third; every runner scores
    HR       everyone scores
These rules undercount runs a little vs. real baseball (runners do take extra
bases), but identically for every staff, so rankings aren't affected.

expected_runs() walks the probability distribution over states exactly (a
Markov chain), so it's deterministic and fast: no Monte Carlo noise in the
ranked score. sample_game() plays one seeded game with the same rules for
the cosmetic reveal.
"""

import itertools
import random

import numpy as np

from warball.matchup import OUTCOMES, Batter, Environment, Pitcher, outcome_probs

N_STATES = 24  # outs * 8 + bases; bases bit 0 = first, bit 1 = second, bit 2 = third


def _advance(outs: int, bases: int, outcome: str) -> tuple[int, int, int]:
    """(outs, bases, runs) after one plate appearance, before inning rollover."""
    if outcome in ("K", "OUT"):
        return outs + 1, bases, 0
    if outcome == "BB":
        if bases & 1 == 0:
            return outs, bases | 1, 0
        if bases & 2 == 0:
            return outs, bases | 3, 0
        if bases & 4 == 0:
            return outs, 7, 0
        return outs, 7, 1
    if outcome == "HR":
        return outs, 0, 1 + bin(bases).count("1")
    shift = {"1B": 1, "2B": 2, "3B": 3}[outcome]
    moved = (bases << shift) | (1 << (shift - 1))
    return outs, moved & 7, bin(moved >> 3).count("1")


def _tables():
    """Per-outcome transition matrices and runs scored from each state."""
    transitions = np.zeros((len(OUTCOMES), N_STATES, N_STATES))
    runs = np.zeros((len(OUTCOMES), N_STATES))
    for o, outcome in enumerate(OUTCOMES):
        for state in range(N_STATES):
            outs, bases, scored = _advance(state // 8, state % 8, outcome)
            next_state = 0 if outs == 3 else outs * 8 + bases
            transitions[o, state, next_state] = 1.0
            runs[o, state] = scored
    return transitions, runs


TRANSITIONS, RUNS_SCORED = _tables()


def _expected_runs_sequence(pa_probs: list[np.ndarray]) -> np.ndarray:
    """Expected runs scored on each plate appearance of a fixed sequence, starting from 0 outs, bases empty."""
    dist = np.zeros(N_STATES)
    dist[0] = 1.0
    per_pa = np.empty(len(pa_probs))
    for i, p in enumerate(pa_probs):
        per_pa[i] = dist @ (p @ RUNS_SCORED)
        dist = dist @ np.tensordot(p, TRANSITIONS, axes=1)
    return per_pa


def matchup_table(lineup: list[Batter], staff: list[Pitcher], env: Environment, probs=outcome_probs) -> np.ndarray:
    """Outcome probabilities for every (pitcher, batter) pair: shape (len(staff), len(lineup), len(OUTCOMES)).

    probs(batter, pitcher, env) -> {outcome: probability} is the plate-appearance
    model: matchup.outcome_probs by default, arsenal.outcome_probs for Theme C.
    """
    return np.array([[[probs(b, p, env)[o] for o in OUTCOMES] for b in lineup] for p in staff])


def expected_runs(lineup: list[Batter], staff: list[Pitcher], env: Environment, probs=outcome_probs) -> dict:
    """Expected runs when each pitcher faces the lineup once through, in turn.

    The base-out state carries across pitching changes, so the order the arms
    pitch in matters slightly. To make the score depend only on *which*
    pitchers were drafted, it's averaged over every order.

    Returns the total plus each pitcher's and each batter's share of it.
    """
    return expected_runs_from_table(matchup_table(lineup, staff, env, probs))


def expected_runs_from_table(table: np.ndarray) -> dict:
    """expected_runs() for a precomputed matchup_table (staff x lineup x OUTCOMES)."""
    n_staff, n_lineup = table.shape[:2]
    per_pitcher = np.zeros(n_staff)
    per_batter = np.zeros(n_lineup)
    orders = list(itertools.permutations(range(n_staff)))
    for order in orders:
        sequence = [table[p, b] for p in order for b in range(n_lineup)]
        runs = _expected_runs_sequence(sequence).reshape(n_staff, n_lineup)
        per_pitcher[list(order)] += runs.sum(axis=1)
        per_batter += runs.sum(axis=0)
    per_pitcher /= len(orders)
    per_batter /= len(orders)
    return {"total": float(per_pitcher.sum()), "per_pitcher": per_pitcher, "per_batter": per_batter}


def sample_game(lineup: list[Batter], staff: list[Pitcher], env: Environment, seed: str, probs=outcome_probs) -> list[dict]:
    """One seeded play-through of the same sequence (cosmetic; never ranked)."""
    return sample_game_from_table(matchup_table(lineup, staff, env, probs), seed)


def sample_game_from_table(table: np.ndarray, seed: str) -> list[dict]:
    rng = random.Random(seed)
    outs, bases, inning, events = 0, 0, 1, []
    for p in range(table.shape[0]):
        for b in range(table.shape[1]):
            outcome = rng.choices(OUTCOMES, weights=table[p, b])[0]
            outs, bases, scored = _advance(outs, bases, outcome)
            events.append({"pitcher": p, "batter": b, "inning": inning, "outcome": outcome, "runs": scored})
            if outs == 3:
                outs, bases, inning = 0, 0, inning + 1
    return events
