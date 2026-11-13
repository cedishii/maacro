"""General mode settings, saved to general_config.json."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import MacroConfig

GENERAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / "general_config.json"


@dataclass
class GeneralConfig(MacroConfig):
    # Use the saved placement zones (and the walk some maps need to line
    # them up). Off: automatic spots, and the character never moves.
    use_map_zones: bool = True

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
