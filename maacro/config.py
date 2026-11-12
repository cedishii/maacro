"""Macro settings, edited on the Configs page and saved to config.json."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
VALID_KEYS = ("1", "2", "3", "4", "5", "6")


@dataclass
class MacroConfig:
    # Placing units: hotbar keys in the order to place them.
    placement_order: list[str] = field(default_factory=lambda: ["6", "5", "5", "5", "1", "1"])
    # Unit name per hotbar key, as shown in the unit manager (used for upgrade priority).
    unit_names: dict[str, str] = field(default_factory=lambda: {
        "1": "Elyssia", "2": "", "3": "", "4": "", "5": "C.E.O.", "6": "Bulby"})
    # Upgrade these keys' units first, in this order; others after.
    upgrade_priority: list[str] = field(default_factory=lambda: ["6", "5", "1"])

    place_units: bool = True
    # When started mid-match: False = check each unit's counter and place what's
    # missing (the counters are reliable now); True = assume the units are down.
    skip_placing_mid_match: bool = False
    upgrade_units: bool = True
    auto_card_pick: bool = True
    auto_vote_start: bool = True

    zoom_out_seconds: float = 1.5   # hold O this long at the start of a match (0 = don't)

    walk_key: str = "w"
    walk_sprint: bool = True        # hold Shift while walking to the ring (runs faster)
    walk_timeout: float = 10.0      # seconds to hold W before giving up
    teleport_wait: float = 2.5      # seconds after clicking Play

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "MacroConfig":
        config = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return config
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def parse_keys(text: str) -> list[str]:
    """'6 5 5 5 1 1' or '6,5,5,5,1,1' → ['6','5','5','5','1','1']. Raises ValueError."""
    keys = text.replace(",", " ").split()
    bad = [k for k in keys if k not in VALID_KEYS]
    if bad:
        raise ValueError(f"Only keys 1–6 are allowed (got {', '.join(bad)}).")
    return keys
