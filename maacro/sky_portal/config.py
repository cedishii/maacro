"""Sky Portal settings, saved to sky_portal_config.json."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import MacroConfig
from ..general.config import GeneralConfig

SKY_PORTAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "sky_portal_config.json"


@dataclass
class SkyPortalConfig(GeneralConfig):
    # Bulby first, the 3 C.E.O.s, 2 Elyssia, then 3 Phoenix (Marco). Water
    # Goddess (2) and Fishi (3) aren't placed.
    placement_order: list[str] = field(default_factory=lambda: ["6", "5", "5", "5", "1", "1", "4", "4", "4"])
    unit_names: dict[str, str] = field(default_factory=lambda: {
        "1": "Elyssia", "2": "Water Goddess", "3": "Fishi", "4": "Phoenix", "5": "C.E.O.", "6": "Bulby"})
    upgrade_priority: list[str] = field(default_factory=lambda: ["6", "5", "4", "1"])
    # Farm units: maxed before any other unit is upgraded (farm_first.py).
    farm_units: list[str] = field(default_factory=lambda: ["6", "5"])
    # Upgrade these units only up to this many upgrades (segments on their bar
    # in the Unit Overview); others go to Max.
    upgrade_caps: dict[str, int] = field(default_factory=lambda: {"1": 2})
    # Walk from the spawn to the placing spot during Vote start, holding Shift
    # (walk_sprint): [key, seconds] steps.
    walk_route: list = field(default_factory=lambda: [["w", 4.0], ["a", 3.0], ["w", 2.0]])
    auto_card_pick: bool = False
    auto_vote_start: bool = True        # the vote is everyone's, not the leader's

    @classmethod
    def load(cls, path: Path = SKY_PORTAL_CONFIG_PATH) -> "SkyPortalConfig":
        # No file yet: the Sky Portal defaults above (not General's "copy the
        # Summer units" first use — Summer has no Fishi).
        return MacroConfig.load.__func__(cls, path) if path.exists() else cls()

    def save(self, path: Path = SKY_PORTAL_CONFIG_PATH) -> None:
        super().save(path)
