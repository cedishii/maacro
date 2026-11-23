"""General mode settings, saved to general_config.json."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import MacroConfig

GENERAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "general_config.json"


@dataclass
class GeneralConfig(MacroConfig):
    # Use the saved placement zones (and the walk some maps need to line
    # them up). Off: automatic spots, and the character never moves.
    use_map_zones: bool = True
    # The game's own auto upgrade (T, update 21.5) instead of MAACRO's upgrading.
    game_auto_upgrade: bool = False
    # Your own "on this screen, click/press this" rules (the Actions page).
    actions: list = field(default_factory=list)
    # After a match: "none" = leave it to you, "replay" = press Replay/Retry,
    # "next" = press Next Stage (Replay if there's no next stage).
    after_match: str = "none"
    # Per unit (hotbar key → number; see unit_plan.py): upgrade only up to
    # this many upgrades, and don't place / upgrade before this wave.
    upgrade_caps: dict[str, int] = field(default_factory=dict)
    place_from_wave: dict[str, int] = field(default_factory=dict)
    upgrade_from_wave: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = GENERAL_CONFIG_PATH) -> "GeneralConfig":
        if not path.exists():
            # First use: the Summer unit setup, but nothing beyond placing,
            # upgrading and waiting.
            config = cls()
            for key, value in vars(MacroConfig.load()).items():
                setattr(config, key, value)
            config.auto_card_pick = False
            config.auto_vote_start = False
            return config
        return super().load.__func__(cls, path)

    def save(self, path: Path = GENERAL_CONFIG_PATH) -> None:
        super().save(path)
