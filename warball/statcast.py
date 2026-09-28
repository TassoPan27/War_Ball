"""
Statcast pipeline for Daily Mode Theme C (Great Pitchers).

1. pull: every regular-season pitch from Baseball Savant (via pybaseball),
   one season at a time in CHUNK_DAYS chunks, reduced on the fly to the few
   columns the model needs and saved as data/statcast/pitches_<year>.csv.gz.
   A finished season is never pulled again, so an interrupted pull resumes
   at the season it stopped in. Expect roughly 10-30 minutes per season.
2. aggregate: per-player, per-pitch-group counts of plate-appearance
   outcomes (see arsenal.COUNT_COLUMNS) plus swings and whiffs, for batters
   and pitchers, saved to data/processed/statcast_{batters,pitchers}.csv.

Outcome mapping mirrors the Lahman side (careers.py): walks and HBP share the
BB bucket downstream, reaching on an error is an out in play, and sacrifice
bunts and intentional walks are left out (neither says anything about a
hitter vs. a pitch type, and Lahman's league PA excludes bunts too).

Usage:
    python -m warball.statcast               # pull any missing seasons, then aggregate
    python -m warball.statcast --aggregate   # aggregate the seasons already pulled
"""

import datetime
import sys

import pandas as pd

from warball.arsenal import COUNT_COLUMNS, PITCH_GROUP
from warball.careers import REFERENCE_YEARS
from warball.data import DATA_DIR, PROCESSED_DIR

YEARS = range(REFERENCE_YEARS[0], REFERENCE_YEARS[1] + 1)
STATCAST_DIR = DATA_DIR.parent / "statcast"
NAMES_FILE = STATCAST_DIR / "names.csv"
BATTERS_FILE = PROCESSED_DIR / "statcast_batters.csv"
PITCHERS_FILE = PROCESSED_DIR / "statcast_pitchers.csv"

CHUNK_DAYS = 7
SEASON_START, SEASON_END = (3, 1), (11, 30)  # generous; game_type filters to the regular season

SWINGS = {
    "swinging_strike", "swinging_strike_blocked", "foul", "foul_tip",
    "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
}
WHIFFS = {"swinging_strike", "swinging_strike_blocked"}

OUTCOME = {
    "strikeout": "K", "strikeout_double_play": "K",
    "walk": "BB",
    "hit_by_pitch": "HBP",
    "home_run": "HR",
    "single": "1B", "double": "2B", "triple": "3B",
    **dict.fromkeys(
        [
            "field_out", "force_out", "grounded_into_double_play", "double_play", "triple_play",
            "fielders_choice", "fielders_choice_out", "field_error", "sac_fly", "sac_fly_double_play",
        ],
        "OUT",
    ),
}


def season_file(year: int):
    return STATCAST_DIR / f"pitches_{year}.csv.gz"


def reduce(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw Statcast pitches -> one small row per regular-season pitch of a known pitch group."""
    df = raw[raw["game_type"] == "R"]
    out = pd.DataFrame({
        "year": df["game_year"].astype(int),
        "batter": df["batter"].astype(int),
        "pitcher": df["pitcher"].astype(int),
        "group": df["pitch_type"].map(PITCH_GROUP),
        "swing": df["description"].isin(SWINGS).astype(int),
        "whiff": df["description"].isin(WHIFFS).astype(int),
        "outcome": df["events"].map(OUTCOME),
    })
    return out[out["group"].notna()]


def pull_season(year: int) -> None:
    from pybaseball import statcast  # network dependency, only needed here

    path = season_file(year)
    if path.exists():
        print(f"{year}: already pulled")
        return
    STATCAST_DIR.mkdir(parents=True, exist_ok=True)
    day, end = datetime.date(year, *SEASON_START), datetime.date(year, *SEASON_END)
    parts = []
    while day <= end:
        chunk_end = min(day + datetime.timedelta(days=CHUNK_DAYS - 1), end)
        raw = statcast(day.isoformat(), chunk_end.isoformat(), verbose=False)
        if raw is not None and not raw.empty:
            parts.append(reduce(raw))
        print(f"{year}: through {chunk_end}", flush=True)
        day = chunk_end + datetime.timedelta(days=1)
    pitches = pd.concat(parts, ignore_index=True)
    tmp = path.with_name(path.name + ".partial")
    pitches.to_csv(tmp, index=False, compression="gzip")
    tmp.rename(path)  # only a complete season ever lands at the real path
    print(f"{year}: {len(pitches):,} pitches, {pitches['outcome'].notna().sum():,} plate appearances")


def load_pitches(years=YEARS) -> pd.DataFrame:
    missing = [y for y in years if not season_file(y).exists()]
    if missing:
        raise FileNotFoundError(f"Statcast seasons not pulled yet: {missing}. Run python -m warball.statcast")
    return pd.concat([pd.read_csv(season_file(y)) for y in years], ignore_index=True)


def counts_by_group(pitches: pd.DataFrame, role: str) -> pd.DataFrame:
    """One row per (player, pitch group): outcome counts, PA, swings, whiffs. role is 'batter' or 'pitcher'."""
    pa = pitches[pitches["outcome"].notna()]
    outcomes = [c for c in COUNT_COLUMNS if c != "PA"]
    counts = pd.crosstab([pa[role], pa["group"]], pa["outcome"]).reindex(columns=outcomes, fill_value=0)
    counts["PA"] = counts.sum(axis=1)
    swings = pitches.groupby([role, "group"])[["swing", "whiff"]].sum().rename(columns={"swing": "swings", "whiff": "whiffs"})
    out = swings.join(counts, how="left").fillna(0).astype(int).reset_index()
    years = pitches.groupby(role)["year"].agg(first_year="min", last_year="max")
    return out.rename(columns={role: "player"}).merge(years, left_on="player", right_index=True)


def _display_name(first: str, last: str) -> str:
    name = f"{first} {last}".strip()
    return name.title() if name.islower() else name  # older register copies are lower-cased


def player_names(ids: set[int]) -> pd.Series:
    """MLBAM id -> "First Last", from the Chadwick register (cached in NAMES_FILE)."""
    cached = pd.read_csv(NAMES_FILE).set_index("player")["name"] if NAMES_FILE.exists() else pd.Series(dtype=str)
    missing = ids - set(cached.index)
    if missing:
        from pybaseball import chadwick_register  # network dependency

        register = chadwick_register()
        register = register[register["key_mlbam"].isin(missing)]
        found = pd.Series(
            [_display_name(str(f), str(l)) for f, l in zip(register["name_first"].fillna(""), register["name_last"].fillna(""))],
            index=register["key_mlbam"].astype(int),
        )
        cached = pd.concat([cached, found])
        cached = cached[~cached.index.duplicated()]
        STATCAST_DIR.mkdir(parents=True, exist_ok=True)
        cached.rename_axis("player").rename("name").to_csv(NAMES_FILE)
    return cached


def aggregate(years=YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    pitches = load_pitches(years)
    batters = counts_by_group(pitches, "batter")
    pitchers = counts_by_group(pitches, "pitcher")
    names = player_names(set(batters["player"]) | set(pitchers["player"]))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for df, path in ((batters, BATTERS_FILE), (pitchers, PITCHERS_FILE)):
        df["name"] = df["player"].map(names).fillna(df["player"].astype(str))
        df.to_csv(path, index=False)
    return batters, pitchers


if __name__ == "__main__":
    if "--aggregate" not in sys.argv:
        for year in YEARS:
            pull_season(year)
    b, p = aggregate()
    print(f"Wrote {b['player'].nunique():,} batters to {BATTERS_FILE.name} and "
          f"{p['player'].nunique():,} pitchers to {PITCHERS_FILE.name} ({b['PA'].sum():,} plate appearances)")
