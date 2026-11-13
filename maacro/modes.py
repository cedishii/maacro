"""The automation modes: one runs at a time, each with its own controller
and settings. Summer Event is the original macro (macro.py), unchanged.

The operating behaviour (Solo / Leader or Party Member, see party.py) is a
separate choice that applies to whichever mode is selected."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import MacroConfig
from .infinity_castle.config import InfinityConfig
from .infinity_castle.controller import InfinityCastleThread
from .macro import MacroThread
from .party import BEHAVIORS, SOLO

MODE_PATH = Path(__file__).resolve().parents[1] / "mode.json"


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    thread_class: type
    config_class: type
    supports_party: bool = True     # works with the Party Member behaviour


MODES = (
    Mode("summer", "Summer Event", MacroThread, MacroConfig),
    Mode("infinity_castle", "Infinity Castle", InfinityCastleThread, InfinityConfig),
)
BY_KEY = {mode.key: mode for mode in MODES}


def _read() -> dict:
    try:
        data = json.loads(MODE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(**changes) -> None:
    data = _read()
    data.update(changes)
    try:
        MODE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def last_mode() -> str:
    key = _read().get("mode")
    return key if key in BY_KEY else MODES[0].key


def save_mode(key: str) -> None:
    _write(mode=key)


def last_behavior() -> str:
    key = _read().get("behavior")
    return key if key in BEHAVIORS else SOLO


def save_behavior(key: str) -> None:
    _write(behavior=key)
