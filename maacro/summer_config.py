"""Summer Event settings: MacroConfig (config.json) plus the card-pick style.
config.py isn't changed; the extra field is saved in the same file."""
from __future__ import annotations

from dataclasses import dataclass

from .config import MacroConfig


@dataclass
class SummerConfig(MacroConfig):
    # "easy": green cards first (red only for + Secret drop chance / Star
    # Golem); "hard": red cards first. See card_strategy.py.
    card_strategy: str = "easy"

    @classmethod
    def load(cls, *args, **kwargs) -> "SummerConfig":
        config = super().load.__func__(cls, *args, **kwargs)
        if config.card_strategy == "secret":      # its first name
            config.card_strategy = "hard"
        return config
