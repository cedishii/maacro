"""Sky Portal settings, saved to sky_portal_config.json."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..general.config import GeneralConfig

SKY_PORTAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "sky_portal_config.json"


@dataclass
class SkyPortalConfig(GeneralConfig):
    # Bulby first, the 3 C.E.O.s, then the damage units: 2 Elyssia, 2 Fishi.
    placement_order: list[str] = field(default_factory=lambda: ["6", "5", "5", "5", "1", "1", "3", "3"])
    unit_names: dict[str, str] = field(default_factory=lambda: {
        "1": "Elyssia", "2": "Water Goddess", "3": "Fishi", "4": "Phoenix", "5": "C.E.O.", "6": "Bulby"})
    upgrade_priority: list[str] = field(default_factory=lambda: ["6", "5", "1", "3"])
    # Farm units: maxed before any other unit is upgraded (farm_first.py).
    farm_units: list[str] = field(default_factory=lambda: ["6", "5"])
    auto_card_pick: bool = False
    auto_vote_start: bool = False

    @classmethod
    def load(cls, path: Path = SKY_PORTAL_CONFIG_PATH) -> "SkyPortalConfig":
        config = super().load.__func__(cls, path)   # defaults above if there's no file yet
        config.auto_vote_start = False      # never votes: the party / the timer starts it
        return config

    def save(self, path: Path = SKY_PORTAL_CONFIG_PATH) -> None:
        self.auto_vote_start = False
        super().save(path)
