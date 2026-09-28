"""
Par for every Daily Mode theme, calibrated empirically: score thousands of
random entries (random staffs from the elite pool, or random lineups from
the hitter pool) against the day's Legends, and put par where
PAR_PERCENTILE of them fall short. If balance feels off, move par, not the
Legends.
"""

import numpy as np

PAR_PERCENTILE = 70  # of entry quality: roughly 30% of random entries beat par
PAR_SAMPLES = 3000
PAR_SEED = "warball-par-calibration"


def calibrate(scores: np.ndarray, lower_is_better: bool = True) -> dict:
    """Par plus a summary of the random entries' score distribution."""
    return {
        "par": float(np.percentile(scores, 100 - PAR_PERCENTILE if lower_is_better else PAR_PERCENTILE)),
        "mean": float(scores.mean()),
        "std": float(scores.std()),
        "best": float(scores.min() if lower_is_better else scores.max()),
        "worst": float(scores.max() if lower_is_better else scores.min()),
        # Score at each percentile 0-100 (ascending), for "better than N% of random entries".
        "percentiles": [float(v) for v in np.percentile(scores, np.arange(101))],
    }


def percentile_rank(score: float, percentiles: list[float]) -> float:
    """Share (0-100) of random entries that scored below this one."""
    return float(np.interp(score, percentiles, np.arange(101)))
