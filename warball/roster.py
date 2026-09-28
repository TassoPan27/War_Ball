"""A drafted Classic Mode team: 9 lineup slots + a 5-man rotation + a 3-man bullpen."""

from dataclasses import dataclass, field
from typing import Mapping

from warball.eligibility import ALL_SLOTS, LINEUP_SLOTS, ROTATION_SLOTS


@dataclass
class Roster:
    filled: dict = field(default_factory=dict)  # index into ALL_SLOTS -> card dict

    def drafted_player_ids(self) -> set:
        return {card["playerID"] for card in self.filled.values()}

    def open_slot_labels(self) -> list[str]:
        return [label for i, label in enumerate(ALL_SLOTS) if i not in self.filled]

    def slots_for(self, card: Mapping) -> list[str]:
        """Distinct open slots this card is eligible for, in lineup-then-staff order."""
        return list(dict.fromkeys(label for label in self.open_slot_labels() if label in card["slots"]))

    def assign(self, card: Mapping, label: str):
        if card["playerID"] in self.drafted_player_ids():
            raise ValueError(f"{card['name']} is already on this roster")
        if label not in card["slots"]:
            raise ValueError(f"{card['name']} isn't eligible at {label}")
        open_indices = [i for i, slot in enumerate(ALL_SLOTS) if slot == label and i not in self.filled]
        if not open_indices:
            raise ValueError(f"No open {label} slot left")
        self.filled[open_indices[0]] = dict(card)

    def is_complete(self) -> bool:
        return len(self.filled) == len(ALL_SLOTS)

    def _cards(self, start: int, stop: int) -> list[dict]:
        return [self.filled[i] for i in range(start, stop) if i in self.filled]

    @property
    def lineup(self) -> list[dict]:
        return self._cards(0, len(LINEUP_SLOTS))

    @property
    def rotation(self) -> list[dict]:
        return self._cards(len(LINEUP_SLOTS), len(LINEUP_SLOTS) + ROTATION_SLOTS)

    @property
    def bullpen(self) -> list[dict]:
        return self._cards(len(LINEUP_SLOTS) + ROTATION_SLOTS, len(ALL_SLOTS))
