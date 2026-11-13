"""The automation modes: one runs at a time, each with its own controller
and settings. Summer Event is the original macro (macro.py), unchanged."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import MacroConfig
from .infinity_castle.config import InfinityConfig
from .infinity_castle.controller import InfinityCastleThread
from .macro import MacroThread

MODE_PATH = Path(__file__).resolve().parents[1] / "mode.json"


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    thread_class: type
    config_class: type


MODES = (
    Mode("summer", "Summer Event", MacroThread, MacroConfig),
    Mode("infinity_castle", "Infinity Castle", InfinityCastleThread, InfinityConfig),
)
BY_KEY = {mode.key: mode for mode in MODES}


def last_mode() -> str:
    try:
        key = json.loads(MODE_PATH.read_text(encoding="utf-8")).get("mode")
    except (OSError, ValueError, AttributeError):
        key = None
    return key if key in BY_KEY else MODES[0].key


def save_mode(key: str) -> None:
    try:
        MODE_PATH.write_text(json.dumps({"mode": key}), encoding="utf-8")
    except OSError:
        pass
