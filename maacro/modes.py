"""The automation modes: one runs at a time, each with its own controller
and settings. Summer Event is the original macro (macro.py), unchanged.

The operating behaviour (Solo / Leader or Party Member, see party.py) is a
separate choice that applies to whichever mode is selected."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .card_first import SummerThread
from .config import MacroConfig
from .general.config import GeneralConfig
from .general.controller import GeneralThread
from .infinity_castle.config import InfinityConfig
from .infinity_castle.controller import InfinityCastleThread
from .macro import MacroThread
from .misty_village import MistyConfig, MistyVillageThread
from .party import BEHAVIORS, SOLO
from .summer_config import SummerConfig
from .sky_portal.config import SkyPortalConfig
from .sky_portal.controller import SkyPortalThread
from .stage_modes import (ChallengeConfig, ChallengeThread, InfiniteConfig, InfiniteThread,
                          StoryConfig, StoryThread)

MODE_PATH = Path(__file__).resolve().parents[1] / "mode.json"


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    thread_class: type
    config_class: type
    supports_party: bool = True     # works with the Party Member behaviour


MODES = (
    Mode("summer", "Summer Event", SummerThread, SummerConfig),
    Mode("infinity_castle", "Infinity Castle", InfinityCastleThread, InfinityConfig),
    # Already leaves every choice to the player, so the Party Member role adds nothing.
    Mode("story", "Story (acts, Next Stage / Retry)", StoryThread, StoryConfig, supports_party=False),
    Mode("infinite", "Infinite (endless waves, Replay)", InfiniteThread, InfiniteConfig,
         supports_party=False),
    Mode("challenge", "Challenge (Replay or back to the lobby)", ChallengeThread, ChallengeConfig,
         supports_party=False),
    Mode("misty_village", "Misty Village (Night when open, else Day)", MistyVillageThread, MistyConfig,
         supports_party=False),
    Mode("general", "Any Stage (legend, raid, portal…)", GeneralThread, GeneralConfig,
         supports_party=False),
    # Always a party member: waits for the leader and the vote, then plays.
    Mode("sky_portal", "Sky Portal (party member)", SkyPortalThread, SkyPortalConfig,
         supports_party=False),
)
BY_KEY = {mode.key: mode for mode in MODES}


# Short names for picking a mode by text (Discord's !mode).
NICKNAMES = {"summer": "summer", "event": "summer", "castle": "infinity_castle", "ic": "infinity_castle",
             "infinity": "infinity_castle", "story": "story", "acts": "story", "infinite": "infinite",
             "inf": "infinite", "endless": "infinite", "challenge": "challenge", "challenges": "challenge",
             "any": "general", "general": "general", "anystage": "general", "legend": "general",
             "raid": "general", "portal": "general", "misty": "misty_village", "village": "misty_village",
             "night": "misty_village", "day": "misty_village", "sky": "sky_portal", "skyportal": "sky_portal"}


def find_mode(text: str) -> str | None:
    """"inf" → "infinite", "Infinity Castle" → "infinity_castle"; None if unclear."""
    word = "".join(ch for ch in (text or "").lower() if ch.isalnum())
    if not word:
        return None
    if word in NICKNAMES:
        return NICKNAMES[word]
    for mode in MODES:
        if word in (mode.key.replace("_", ""), "".join(ch for ch in mode.label.lower() if ch.isalnum())):
            return mode.key
    starts = {key for nick, key in NICKNAMES.items() if nick.startswith(word) and len(word) >= 3}
    return starts.pop() if len(starts) == 1 else None


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


def light_mode() -> bool:
    """Light mode (Settings): fewer pictures and screen reads, for slower PCs."""
    return bool(_read().get("light_mode", False))


def save_light_mode(on: bool) -> None:
    _write(light_mode=bool(on))
