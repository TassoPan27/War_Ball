"""
Era-adjusted, shrunk career rates for Daily Mode.

1. Every player-season's bucket rates (K, BB incl. HBP, HR, BIP; see
   matchup.py) are converted to one reference environment with the odds-ratio
   method *before* aggregating:
       adj_odds = odds(player) * odds(reference) / odds(that season's league)
   then renormalized to sum to 1.
2. Careers are PA-weighted (batters) or batters-faced-weighted (pitchers)
   averages of those adjusted rates. Rates, never totals, so longevity isn't
   rewarded.
3. Each career is shrunk toward the reference average by adding SHRINK of
   reference-average performance, so short careers can't dominate.

Batters also carry an era-adjusted career mix of non-HR hit types.
"""

import pandas as pd

from warball import data
from warball.data import PROCESSED_DIR
from warball.matchup import BUCKETS, HIT_TYPES, Environment, from_odds, odds

# The reference environment every rate is expressed in: modern AL/NL play.
REFERENCE_YEARS = (2015, 2024)
REFERENCE_LEAGUES = ("AL", "NL")

# Hitter strikeouts weren't recorded consistently in Negro League box scores
# (league batting K rates there have a median of ~1%, vs. 6%+ in every AL/NL
# season since 1900), and odds-ratio adjustment can't work from ~0.
MIN_LEAGUE_BATTER_K_RATE = 0.05

# Shrinkage: PA (batters) or batters faced (pitchers) of reference-average
# performance added to every career, per bucket. Home runs are the noisiest
# bucket, so they get the most. HIT_MIX_SHRINK is in non-HR hits.
BATTER_SHRINK = {"K": 100, "BB": 150, "HR": 250, "BIP": 100}
PITCHER_SHRINK = {"K": 150, "BB": 250, "HR": 600, "BIP": 250}
HIT_MIX_SHRINK = 100

# A pitcher is a starter when at least this share of his career games were starts.
STARTER_GS_SHARE = 0.5

BATTERS_FILE = PROCESSED_DIR / "career_batters.csv"
PITCHERS_FILE = PROCESSED_DIR / "career_pitchers.csv"


def _team_totals(teams: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    cols = ["AB", "H", "2B", "3B", "HR", "BB", "SO", "HBP", "SF", "HRA", "BBA", "SOA"]
    df = teams[keys + cols].copy()
    for col in ("SO", "HBP", "SF"):
        df[col] = df[col].fillna(0)
    return df.groupby(keys).sum(numeric_only=True) if keys else df.sum(numeric_only=True).to_frame().T


def _rates_from_totals(t: pd.DataFrame) -> pd.DataFrame:
    """League bucket rates from team totals: batting side (bat_*) and pitching side (pit_*)."""
    pa = t["AB"] + t["BB"] + t["HBP"] + t["SF"]
    non_hr_hits = t["H"] - t["HR"]
    out = pd.DataFrame(index=t.index)
    out["bat_K"] = t["SO"] / pa
    out["bat_BB"] = (t["BB"] + t["HBP"]) / pa
    out["bat_HR"] = t["HR"] / pa
    out["bat_BIP"] = 1 - out["bat_K"] - out["bat_BB"] - out["bat_HR"]
    out["babip"] = non_hr_hits / (pa * out["bat_BIP"])
    out["mix_2B"] = t["2B"] / non_hr_hits
    out["mix_3B"] = t["3B"] / non_hr_hits
    out["mix_1B"] = 1 - out["mix_2B"] - out["mix_3B"]
    # League PA stands in for batters faced; HBP is only recorded on the batting side.
    out["pit_K"] = t["SOA"] / pa
    out["pit_BB"] = (t["BBA"] + t["HBP"]) / pa
    out["pit_HR"] = t["HRA"] / pa
    out["pit_BIP"] = 1 - out["pit_K"] - out["pit_BB"] - out["pit_HR"]
    return out


def league_rates(teams: pd.DataFrame) -> pd.DataFrame:
    """One row per (yearID, lgID)."""
    return _rates_from_totals(_team_totals(teams, ["yearID", "lgID"])).reset_index()


def reference_environment(teams: pd.DataFrame) -> Environment:
    ref = teams[teams["yearID"].between(*REFERENCE_YEARS) & teams["lgID"].isin(REFERENCE_LEAGUES)]
    r = _rates_from_totals(_team_totals(ref, [])).iloc[0]
    return Environment(
        rates={b: float(r[f"bat_{b}"]) for b in BUCKETS},
        babip=float(r["babip"]),
        hit_mix={t: float(r[f"mix_{t}"]) for t in HIT_TYPES},
    )


def _era_adjust(rates: pd.DataFrame, league: pd.DataFrame, reference: dict) -> pd.DataFrame:
    # A rate of exactly 1 (one hit, and it was a double) has infinite odds; cap it.
    # Such seasons carry almost no weight in a career anyway.
    rates = rates.clip(upper=0.999)
    adjusted = pd.DataFrame(
        {k: from_odds(odds(rates[k]) * odds(reference[k]) / odds(league[k])) for k in reference}, index=rates.index
    )
    return adjusted.div(adjusted.sum(axis=1), axis=0)


def _weighted_career(seasons: pd.DataFrame, cols: list[str], weight: str) -> pd.DataFrame:
    weighted = seasons[cols].mul(seasons[weight], axis=0)
    weighted["playerID"] = seasons["playerID"]
    sums = weighted.groupby("playerID").sum()
    totals = seasons.groupby("playerID")[weight].sum()
    return sums.div(totals, axis=0)


def _shrink(rates: pd.DataFrame, sample: pd.Series, reference: dict, shrink: dict) -> pd.DataFrame:
    shrunk = pd.DataFrame(
        {k: (rates[k] * sample + reference[k] * shrink[k]) / (sample + shrink[k]) for k in reference}, index=rates.index
    )
    return shrunk.div(shrunk.sum(axis=1), axis=0)


def _with_names(df: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    names = people[["playerID", "nameFirst", "nameLast"]].copy()
    names["name"] = (names["nameFirst"].fillna("") + " " + names["nameLast"].fillna("")).str.strip()
    return df.merge(names[["playerID", "name"]], on="playerID", how="left")


def career_batters(batting: pd.DataFrame, raw_batting: pd.DataFrame, lg: pd.DataFrame, env: Environment) -> pd.DataFrame:
    # Seasons where the player's strikeouts weren't recorded (1880s-90s AA/UA) can't be adjusted.
    no_so = raw_batting[raw_batting["SO"].isna()][["playerID", "yearID", "teamID"]].drop_duplicates()
    s = batting.merge(no_so, how="left", indicator=True)
    s = s[(s["_merge"] == "left_only") & (s["PA"] > 0)].drop(columns="_merge")
    s = s.merge(lg, on=["yearID", "lgID"])
    s = s[s["bat_K"] >= MIN_LEAGUE_BATTER_K_RATE]

    rates = pd.DataFrame({
        "K": s["SO"] / s["PA"],
        "BB": (s["BB"] + s["HBP"]) / s["PA"],
        "HR": s["HR"] / s["PA"],
    })
    rates["BIP"] = 1 - rates.sum(axis=1)
    league = s[[f"bat_{b}" for b in BUCKETS]].set_axis(BUCKETS, axis=1)
    adj_cols = [f"adj_{b}" for b in BUCKETS]
    s[adj_cols] = _era_adjust(rates, league, env.rates).values

    careers = _weighted_career(s, adj_cols, "PA").set_axis(BUCKETS, axis=1)

    # Hit-type mix: era-adjusted the same way, weighted by non-HR hits.
    hits = s[s["H"] > s["HR"]].copy()
    hits["non_hr_hits"] = hits["H"] - hits["HR"]
    counts = {"1B": hits["H"] - hits["2B"] - hits["3B"] - hits["HR"], "2B": hits["2B"], "3B": hits["3B"]}
    mix = pd.DataFrame({t: counts[t] / hits["non_hr_hits"] for t in HIT_TYPES})
    mix_league = hits[[f"mix_{t}" for t in HIT_TYPES]].set_axis(HIT_TYPES, axis=1)
    adj_mix_cols = [f"adj_{t}" for t in HIT_TYPES]
    hits[adj_mix_cols] = _era_adjust(mix, mix_league, env.hit_mix).values
    mix_careers = _weighted_career(hits, adj_mix_cols, "non_hr_hits").set_axis(HIT_TYPES, axis=1)

    totals = s.groupby("playerID").agg(
        PA=("PA", "sum"), AB=("AB", "sum"), H=("H", "sum"), b2B=("2B", "sum"), b3B=("3B", "sum"),
        HR_total=("HR", "sum"), first_year=("yearID", "min"), last_year=("yearID", "max"),
    )
    non_hr_hits = hits.groupby("playerID")["non_hr_hits"].sum().reindex(totals.index, fill_value=0)
    mix_careers = mix_careers.reindex(totals.index).fillna(pd.Series(env.hit_mix))
    shrunk = _shrink(careers, totals["PA"], env.rates, BATTER_SHRINK)
    mix_shrunk = _shrink(mix_careers, non_hr_hits, env.hit_mix, {t: HIT_MIX_SHRINK for t in HIT_TYPES})

    out = totals.join(shrunk).join(mix_shrunk.add_prefix("mix_"))
    out["ISO"] = (out["b2B"] + 2 * out["b3B"] + 3 * out["HR_total"]) / out["AB"]
    return out.reset_index()


def career_pitchers(pitching: pd.DataFrame, lg: pd.DataFrame, env: Environment) -> pd.DataFrame:
    s = pitching.merge(lg, on=["yearID", "lgID"]).copy()
    s = s[(s["pit_K"] > 0) & (s["pit_BB"] > 0) & (s["pit_HR"] > 0)]
    # 225 pitcher-seasons have no batters-faced count; estimate it as the spec suggests.
    estimate = s["IP"] * 3 + s["H"] + s["BB"] + s["HBP"]
    s["BF"] = s["BFP"].where(s["BFP"] > 0, estimate)
    s = s[s["BF"] > 0]

    rates = pd.DataFrame({"K": s["SO"] / s["BF"], "BB": (s["BB"] + s["HBP"]) / s["BF"], "HR": s["HR"] / s["BF"]})
    rates["BIP"] = 1 - rates.sum(axis=1)
    league = s[[f"pit_{b}" for b in BUCKETS]].set_axis(BUCKETS, axis=1)
    adj_cols = [f"adj_{b}" for b in BUCKETS]
    s[adj_cols] = _era_adjust(rates, league, env.rates).values

    careers = _weighted_career(s, adj_cols, "BF").set_axis(BUCKETS, axis=1)
    s["FIP_x_IP"] = s["FIP"] * s["IP"]
    s["FIPminus_x_IP"] = s["FIPminus"] * s["IP"]
    totals = s.groupby("playerID").agg(
        BF=("BF", "sum"), IP=("IP", "sum"), G=("G", "sum"), GS=("GS", "sum"), HR_total=("HR", "sum"),
        SO_total=("SO", "sum"), FIP_x_IP=("FIP_x_IP", "sum"), FIPminus_x_IP=("FIPminus_x_IP", "sum"),
        first_year=("yearID", "min"), last_year=("yearID", "max"),
    )
    totals["FIP"] = totals.pop("FIP_x_IP") / totals["IP"]
    totals["FIPminus"] = totals.pop("FIPminus_x_IP") / totals["IP"]
    totals["role"] = (totals["GS"] >= STARTER_GS_SHARE * totals["G"]).map({True: "SP", False: "RP"})
    return totals.join(_shrink(careers, totals["BF"], env.rates, PITCHER_SHRINK)).reset_index()


def build(batting: pd.DataFrame, pitching: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    teams = data.load_teams()
    people = data.load_people()
    lg = league_rates(teams)
    env = reference_environment(teams)
    batters = _with_names(career_batters(batting, data.load_batting(), lg, env), people)
    pitchers = _with_names(career_pitchers(pitching, lg, env), people)
    batters.to_csv(BATTERS_FILE, index=False)
    pitchers.to_csv(PITCHERS_FILE, index=False)
    return batters, pitchers
