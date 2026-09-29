"""End-to-end Daily Mode on synthetic players: build, calibrate par, draft, score (no Lahman or Statcast data)."""

import datetime
import itertools

import numpy as np
import pandas as pd
import pytest

from warball import aces, careers, daily, par, statcast
from warball.arsenal import COUNT_COLUMNS, GROUPS
from warball.matchup import Environment

DATE = datetime.date(2026, 9, 28)
ENV = Environment(
    rates={"K": 0.22, "BB": 0.09, "HR": 0.03, "BIP": 0.66},
    babip=0.29,
    hit_mix={"1B": 0.75, "2B": 0.23, "3B": 0.02},
)


def _normalized(rates):
    total = sum(rates.values())
    return {k: v / total for k, v in rates.items()}


def synthetic_careers(seed=1):
    rng = np.random.default_rng(seed)
    batters = []
    for i in range(300):
        k, bb, hr = rng.uniform(0.04, 0.30), rng.uniform(0.05, 0.16), rng.uniform(0.005, 0.07)
        rates = _normalized({"K": k, "BB": bb, "HR": hr, "BIP": 1 - k - bb - hr})
        pa = int(rng.integers(3000, 12000))
        batters.append({
            "playerID": f"bat{i:03d}", "name": f"Batter {i}", "first_year": 1950, "last_year": 1965,
            "PA": pa, "PA_modern": pa, "AB": int(pa * 0.9), "H": int(pa * 0.9 * rng.uniform(0.24, 0.34)),
            "HR_total": int(pa * hr), "ISO": rng.uniform(0.08, 0.30), **rates,
            "mix_1B": 0.74, "mix_2B": 0.23, "mix_3B": 0.03, "babip": rng.uniform(0.27, 0.35),
        })
    pitchers = []
    for i in range(30):
        k, bb, hr = rng.uniform(0.18, 0.34), rng.uniform(0.04, 0.10), rng.uniform(0.015, 0.035)
        ip = float(rng.integers(1500, 3500))
        pitchers.append({
            "playerID": f"pit{i:02d}", "name": f"Pitcher {i}", "first_year": 1990, "last_year": 2005,
            "role": "SP", "BF": int(ip * 4.2), "IP": ip, "FIP": 3.0, "FIPminus": rng.uniform(65, 80),
            "HR_total": int(ip * 4.2 * hr), **_normalized({"K": k, "BB": bb, "HR": hr, "BIP": 1 - k - bb - hr}),
        })
    return pd.DataFrame(batters).set_index("playerID"), pd.DataFrame(pitchers).set_index("playerID")


def synthetic_statcast(seed=2):
    """Long per-group counts for 40 hitters and 12 pitchers; one pitcher leans hard on a great curveball."""
    rng = np.random.default_rng(seed)
    base = {"K": 0.22, "BB": 0.08, "HBP": 0.01, "HR": 0.03, "1B": 0.14, "2B": 0.045, "3B": 0.004}
    base["OUT"] = 1 - sum(base.values())
    usage = {"FB": 0.55, "SL": 0.2, "CU": 0.1, "CH": 0.15}

    def rows(role_prefix, n, pa_range, skill):
        out = []
        for i in range(n):
            pa_total = int(rng.integers(*pa_range))
            mix = dict(usage)
            if role_prefix == "p" and i == 0:
                mix = {"FB": 0.45, "SL": 0.1, "CU": 0.35, "CH": 0.1}
            for g in GROUPS:
                p = dict(base)
                p["K"] *= skill(i, g)
                p["OUT"] = 1 - sum(v for k, v in p.items() if k != "OUT")
                counts = rng.multinomial(int(pa_total * mix[g]), list(p.values()))
                swings = int(counts.sum() * 2)
                out.append({
                    "player": 1000 * (role_prefix == "p") + i, "group": g, "name": f"{role_prefix}{i}",
                    "first_year": 2015, "last_year": 2024, **dict(zip(p, map(int, counts))),
                    "PA": int(counts.sum()), "swings": swings, "whiffs": int(swings * 0.25),
                })
        return out

    ace_skill = lambda i, g: 1.8 if (i == 0 and g == "CU") else (1.0 + 0.04 * (12 - i))
    batters = pd.DataFrame(rows("b", 40, (1600, 5000), lambda i, g: rng.uniform(0.7, 1.3)))
    pitchers = pd.DataFrame(rows("p", 12, (3200, 6000), ace_skill))
    for df in (batters, pitchers):
        df[list(COUNT_COLUMNS)] = df[list(COUNT_COLUMNS)].astype(int)
    return batters, pitchers


@pytest.fixture
def processed(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(aces, "CHALLENGE_FILE", tmp_path / "daily_aces.json")
    monkeypatch.setattr(statcast, "BATTERS_FILE", tmp_path / "statcast_batters.csv")
    monkeypatch.setattr(statcast, "PITCHERS_FILE", tmp_path / "statcast_pitchers.csv")
    monkeypatch.setattr(careers, "BATTERS_FILE", tmp_path / "career_batters.csv")
    monkeypatch.setattr(careers, "PITCHERS_FILE", tmp_path / "career_pitchers.csv")
    monkeypatch.setattr(par, "PAR_SAMPLES", 200)
    return tmp_path


# ---------- Themes A and B: draft pitchers ----------


def test_legends_must_have_played_mostly_in_the_modern_game():
    batters, _ = synthetic_careers()
    slugger = batters["HR"].idxmax()
    assert slugger in daily.power_candidates(batters, ENV).index

    batters.loc[slugger, "PA_modern"] = batters.loc[slugger, "PA"] * 0.4  # 60% of his career before 1893
    picked = daily.power_candidates(batters, ENV)
    assert slugger not in picked.index and len(picked) == daily.LEGEND_CANDIDATES

    with pytest.raises(KeyError):
        daily.power_candidates(batters.drop(columns="PA_modern"), ENV)


def test_deal_lineups_needs_enough_candidates():
    batters, _ = synthetic_careers()
    with pytest.raises(ValueError):
        daily.deal_lineups(batters.head(10))
    lineups = daily.deal_lineups(batters.head(45))
    assert len(lineups) == daily.LINEUPS and all(len(l) == daily.LINEUP_SIZE for l in lineups)


@pytest.mark.parametrize("key", list(daily.STAFF_THEMES))
def test_staff_theme_end_to_end(processed, key):
    batters, pitchers = synthetic_careers()
    theme = daily.STAFF_THEMES[key]
    daily.build_theme(theme, batters, pitchers, ENV)
    challenge = daily.StaffChallenge(theme, batters, pitchers)

    card = challenge.challenge(DATE)
    assert card["kind"] == "staff" and card["lever"] == theme.lever and len(card["pool"]) == daily.POOL_SIZE

    lineup, pool = challenge.day(DATE)
    staffs = list(itertools.combinations(pool, daily.STAFF_SIZE))[:25]
    results = [challenge.simulate(DATE, list(s)) for s in staffs]
    r = results[0]
    assert r == challenge.simulate(DATE, list(staffs[0]))
    assert challenge.simulate(DATE, list(reversed(staffs[0])))["score"] == pytest.approx(r["score"])
    assert r["average"] - r["rawQuality"] - r["matchupEdge"] == pytest.approx(r["score"])
    assert 0 <= r["betterThanPct"] <= 100
    assert r["sampleRows"] and len(r["sampleGame"]) == daily.STAFF_SIZE * daily.LINEUP_SIZE

    with pytest.raises(ValueError):
        challenge.simulate(DATE, list(pool[:2]))


# ---------- Theme C: draft hitters ----------


def build_aces(processed):
    batters, pitchers = synthetic_statcast()
    batters.to_csv(statcast.BATTERS_FILE, index=False)
    pitchers.to_csv(statcast.PITCHERS_FILE, index=False)
    return aces.build()


def test_curveball_ace_is_found_and_his_curve_is_his_signature(processed):
    stored = build_aces(processed)
    assert len(stored["aces"]) == aces.ACES
    by_id = {a["id"]: a for a in stored["aces"]}
    assert "1000" in by_id and by_id["1000"]["signature"] == "CU"
    for a in stored["aces"]:
        assert a["groups"][a["signature"]]["usage"] >= aces.SIGNATURE_MIN_USAGE


def test_ace_theme_end_to_end(processed):
    build_aces(processed)
    challenge = aces.AceChallenge()
    card = challenge.challenge(DATE)
    assert card["kind"] == "lineup" and len(card["pool"]) == aces.POOL_SIZE
    assert card["ace"]["signature"] in GROUPS

    _, pool = challenge.day(DATE)
    picks = pool[: aces.LINEUP_SIZE]
    r = challenge.simulate(DATE, picks)
    assert r == challenge.simulate(DATE, picks)
    assert r["average"] + r["rawQuality"] + r["matchupEdge"] == pytest.approx(r["score"])
    assert sum(h["runs"] for h in r["hitters"]) == pytest.approx(r["score"])
    assert len(r["sampleGame"]) == aces.LINEUP_SIZE * aces.TIMES_THROUGH
    assert {e["pitcher"] for e in r["sampleGame"]} == set(range(aces.TIMES_THROUGH))
    assert {e["batter"] for e in r["sampleGame"]} == set(range(aces.LINEUP_SIZE))

    with pytest.raises(ValueError):
        challenge.simulate(DATE, picks[:8])
    with pytest.raises(ValueError):
        challenge.simulate(DATE, picks[:8] + [picks[0]])


def test_rotation_covers_every_built_theme(processed):
    batters, pitchers = synthetic_careers()
    batters.reset_index().to_csv(careers.BATTERS_FILE, index=False)
    pitchers.reset_index().to_csv(careers.PITCHERS_FILE, index=False)
    for theme in daily.STAFF_THEMES.values():
        daily.build_theme(theme, batters, pitchers, ENV)
    build_aces(processed)

    challenge = daily.DailyChallenge()
    n = len(daily.THEME_ROTATION)
    keys = [challenge.theme_key(DATE + datetime.timedelta(days=i)) for i in range(2 * n)]
    assert set(keys) == set(daily.THEME_ROTATION) and keys[:n] == keys[n:]
    assert challenge.challenge(DATE, "aces")["kind"] == "lineup"
    with pytest.raises(ValueError):
        challenge.challenge(DATE, "nope")
