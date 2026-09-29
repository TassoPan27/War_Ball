"""Card tier boundaries (warball/tiers.py)."""

import pytest

from warball.tiers import coach_tier, hitter_tier, pitcher_tier


@pytest.mark.parametrize("war, tier", [(-1.0, "bronze"), (1.9, "bronze"), (2.0, "silver"), (4.0, "gold"), (5.9, "gold"), (6.0, "diamond"), (12.0, "diamond")])
def test_hitter_tiers(war, tier):
    assert hitter_tier(war) == tier


@pytest.mark.parametrize("fip_minus, tier", [(140, "bronze"), (100.1, "bronze"), (100, "silver"), (85, "gold"), (70.1, "gold"), (70, "diamond"), (45, "diamond")])
def test_pitcher_tiers(fip_minus, tier):
    assert pitcher_tier(fip_minus) == tier


@pytest.mark.parametrize("wins, tier", [(-3.0, "bronze"), (-0.1, "bronze"), (0.0, "silver"), (2.0, "gold"), (3.9, "gold"), (4.0, "diamond")])
def test_coach_tiers(wins, tier):
    assert coach_tier(wins) == tier
