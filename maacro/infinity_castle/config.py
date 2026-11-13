"""Infinity Castle settings, saved to ic_config.json (Summer keeps config.json)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import MacroConfig

IC_CONFIG_PATH = Path(__file__).resolve().parents[2] / "ic_config.json"


@dataclass
class InfinityConfig(MacroConfig):
    # Hotbar keys of damage units: they go in the circled path zones first;
    # every other unit is placed away from them (so the zones stay free).
    path_units: list[str] = field(default_factory=lambda: ["1"])
    # Money comes fast here: place and upgrade at twice the Summer pace.
    fast_economy: bool = True

    @classmethod
    def load(cls, path: Path = IC_CONFIG_PATH) -> "InfinityConfig":
        if not path.exists():
            # First use: start from the Summer settings (units, names, switches).
            config = cls()
            for key, value in vars(MacroConfig.load()).items():
                setattr(config, key, value)
            config.auto_card_pick = False      # no cards in Infinity Castle
            return config
        return super().load.__func__(cls, path)

    def save(self, path: Path = IC_CONFIG_PATH) -> None:
        super().save(path)
