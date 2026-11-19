"""App-wide settings (Settings page), saved to app_settings.json.

Per-mode unit setups live in each mode's own config file; these are the
settings that apply whatever mode runs: session goals, hotkeys, the Roblox
server link and auto-rejoin.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "app_settings.json"
HOTKEYS = tuple(f"F{n}" for n in range(1, 13))


def hotkey_vk(name: str) -> int | None:
    """Virtual-key code of "F1"…"F12" (None for anything else)."""
    name = (name or "").strip().upper()
    return 0x70 + HOTKEYS.index(name) if name in HOTKEYS else None


@dataclass
class AppSettings:
    # Session goals: stop by itself once one is reached (0 = off).
    stop_after_runs: int = 0
    stop_after_minutes: int = 0
    stop_after_losses_in_row: int = 0
    close_roblox_at_goal: bool = False      # also close Roblox when a goal stops the macro

    # Hotkeys (work while Roblox is in front).
    start_key: str = "F1"
    stop_key: str = "F3"

    # Roblox: where to (re)join, and when to do it by itself.
    server_link: str = ""                   # private server link; empty = a public server
    rejoin: bool = False
    rejoin_closed_seconds: int = 60         # Roblox closed / crashed this long → open it again
    rejoin_disconnected_seconds: int = 120  # "Disconnected" box this long → restart Roblox
    rejoin_stuck_minutes: int = 0           # stuck on one screen this long → restart (0 = off)

    # Profiles named after a map are used by themselves on that map.
    auto_profiles: bool = True

    # Discord remote control (a bot of your own; see remote.py).
    remote_enabled: bool = False
    remote_token: str = ""
    remote_channel: str = ""
    remote_user: str = ""

    @classmethod
    def load(cls, path: Path = APP_SETTINGS_PATH) -> "AppSettings":
        settings = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return settings
        if not isinstance(data, dict):
            return settings
        for f in fields(cls):
            if f.name in data:
                value = data[f.name]
                default = getattr(settings, f.name)
                # Keep the default when the saved value has the wrong type.
                if isinstance(default, bool):
                    if isinstance(value, bool):
                        setattr(settings, f.name, value)
                elif isinstance(default, int):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        setattr(settings, f.name, max(0, int(value)))
                elif isinstance(value, str):
                    setattr(settings, f.name, value)
        if hotkey_vk(settings.start_key) is None:
            settings.start_key = "F1"
        if hotkey_vk(settings.stop_key) is None or settings.stop_key == settings.start_key:
            settings.stop_key = "F3" if settings.start_key != "F3" else "F4"
        return settings

    def save(self, path: Path = APP_SETTINGS_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
