"""Keeping a long, unattended session alive (Settings → Overnight).

  Keep the PC awake    While the macro runs, Windows is told not to sleep or
                       turn the screen off (SetThreadExecutionState). A locked
                       or sleeping PC gives black pictures, so the night is lost.
  Resume after a crash If MAACRO closes while the macro runs and it wasn't you
                       (a crash, a Windows Update restart), it starts again by
                       itself the next time it opens. A small file
                       (running.json) says "running" from Start until Stop.
  Start with Windows   A launcher in the Startup folder, so MAACRO opens after
                       a restart (and, with the one above, carries on).
  Start at             A clock time to press Start by itself (once a day).
  Fresh Roblox         Restart Roblox every N hours, only between matches
                       (lobby or the screen after a match): a long-running
                       client gets slow and crashes more.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from .goals import parse_time

ROOT = Path(__file__).resolve().parents[1]
RUN_FLAG = ROOT / "running.json"
RESUME_WITHIN_HOURS = 12        # an older "running" mark is ignored
RESUME_DELAY = 20               # s to wait (and let you press Stop) before resuming
SAFE_SCREENS = ("lobby", "after_end")
SAFE_FOR = 5.0                  # s on a safe screen before a fresh restart (the run is recorded)
LAUNCHER_NAME = "MAACRO.cmd"

_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED, _ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002


def keep_awake(on: bool) -> bool:
    """Ask Windows not to sleep / turn the screen off (on) or allow it again."""
    flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED if on else 0)
    try:
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except (AttributeError, OSError):
        return False


# --- the "running" mark --------------------------------------------------
def mark_running(mode: str, path: Path | None = None) -> None:
    path = path or RUN_FLAG
    try:
        path.write_text(json.dumps({"mode": mode, "since": time.time()}), encoding="utf-8")
    except OSError:
        pass


def clear_running(path: Path | None = None) -> None:
    path = path or RUN_FLAG
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def interrupted_session(path: Path | None = None, now: float | None = None) -> dict | None:
    """The session that was running when MAACRO last closed without a Stop
    ({"mode", "since"}), or None (none, unreadable, or too old)."""
    path = path or RUN_FLAG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("since"), (int, float)):
        return None
    age = (now if now is not None else time.time()) - data["since"]
    if not 0 <= age <= RESUME_WITHIN_HOURS * 3600:
        return None
    return data


# --- start with Windows -----------------------------------------------------
def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / \
        "Programs" / "Startup"


def launcher_text(root: Path = ROOT) -> str:
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    exe = pythonw if pythonw.exists() else Path(sys.executable).with_name("pythonw.exe")
    return (f'@echo off\r\ncd /d "{root}"\r\nstart "" "{exe}" "{root / "main.py"}"\r\n')


def start_with_windows(on: bool, folder: Path | None = None) -> None:
    """Add (or remove) the launcher in the Startup folder. Raises OSError."""
    path = (folder or startup_dir()) / LAUNCHER_NAME
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(launcher_text(), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def starts_with_windows(folder: Path | None = None) -> bool:
    return ((folder or startup_dir()) / LAUNCHER_NAME).exists()


# --- start at a clock time ----------------------------------------------------
def start_due(start_at: str, now: datetime, last_started: date | None) -> bool:
    """It's past `start_at` today (within an hour) and it hasn't fired today."""
    hm = parse_time(start_at)
    if hm is None or last_started == now.date():
        return False
    target = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return 0 <= (now - target).total_seconds() < 3600


# --- fresh Roblox ---------------------------------------------------------------
class FreshRestart:
    """Says when to restart Roblox: every `hours`, on a safe screen only."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.since = clock()            # Roblox (re)opened / the session started
        self._safe_since: float | None = None

    def reset(self) -> None:
        self.since = self._clock()
        self._safe_since = None

    def due(self, hours: float, running: bool, screen: str | None) -> bool:
        now = self._clock()
        if screen in SAFE_SCREENS:
            if self._safe_since is None:
                self._safe_since = now
        else:
            self._safe_since = None
        if not (hours and running) or now - self.since < hours * 3600:
            return False
        return self._safe_since is not None and now - self._safe_since >= SAFE_FOR
