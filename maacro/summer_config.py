"""Summer Event settings: MacroConfig (config.json) plus the card-pick style.
config.py isn't changed; the extra field is saved in the same file."""
from __future__ import annotations

from dataclasses import dataclass

from .config import MacroConfig


@dataclass
class SummerConfig(MacroConfig):
    # "easy": green cards first (red only for Secret Portal chance / Star
    # Golem); "secret": red cards first. See card_strategy.py.
    card_strategy: str = "easy"
