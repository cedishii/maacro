"""Summer Event settings: MacroConfig (config.json) plus the card-pick style.
config.py isn't changed; the extra field is saved in the same file."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import MacroConfig


@dataclass
class SummerConfig(MacroConfig):
    # "easy": green cards first (red only for + Secret drop chance / Star
    # Golem); "hard": red cards first; "smart": Hard, Easy for 2 runs after a
    # defeat. See card_strategy.py.
    card_strategy: str = "easy"
    # Per unit (hotbar key → number; see unit_plan.py): upgrade only up to
    # this many upgrades, and don't place / upgrade before this wave.
    upgrade_caps: dict[str, int] = field(default_factory=dict)
    place_from_wave: dict[str, int] = field(default_factory=dict)
    upgrade_from_wave: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, *args, **kwargs) -> "SummerConfig":
        config = super().load.__func__(cls, *args, **kwargs)
        if config.card_strategy == "secret":      # its first name
            config.card_strategy = "hard"
        return config
