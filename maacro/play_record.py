"""Record how you play a map, then let MAACRO play it the same way.

Recording (Main page → Record, or say yes when a new map comes up):
  starts when the match starts (the vote is over, the first match screen
  shows) and stops when you leave it (Return to lobby → loading / lobby).
  Everything you do in Roblox is read from the real keyboard and mouse
  (raw_input.py — read only; MAACRO's own clicks are left out): keys, clicks
  with where they were (as a fraction of the window, so it fits any size),
  the wheel, and camera turns (mouse movement while the right button is held).
  Card votes aren't recorded — your card strategy picks those.

Each action is stamped with the wave it happened in and the seconds since
that wave began, not the seconds since the start: when MAACRO plays it back,
an action waits for its wave, so a slower or faster run stays in step (a
wave that comes early brings its actions with it; one that's late holds
them back).

Playing (Settings → Your own play): on a recorded map, the mode's own placing
and upgrading is replaced by your recording during the match; everything
else (lobby, matchmaking, cards, results, rejoin) works as usual.

recordings/<map>.json, one per map and stage kind ("fiend_city_summer_hunt").
"""
from __future__ import annotations

import ctypes
import functools
import json
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .control import input as inp
from .history import split_map
from .maps import slugify
from .raw_input import RawInput
from .vision.ocr import OcrLine
from .vision.screens import fuzzy_in

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS_DIR = ROOT / "recordings"
RECORD_SCREENS = ("in_match", "unit_manager")      # card votes are the card strategy's
SKIP_SCANS = {0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x57, 0x58,  # F1–F12
              0x38}                                                                   # Alt
SKIP_EXTENDED = {0x5B, 0x5C, 0x5D}                 # the Windows and menu keys
TAB, ALT = 0x0F, 0x38
MOVE_EVERY = 0.03       # s: camera movement is saved in pieces this long
MAP_WAIT = 6.0          # s into a match to wait for the map name before playing normally


# --- the map ------------------------------------------------------------------
def loading_title(lines: list[OcrLine], width: int, height: int) -> str:
    """"Fiend City Summer Hunt" from the loading screen ("Travelling to… /
    Fiend City / Summer Hunt / Weather: Windy"); "" if it isn't there."""
    anchor = next((l for l in lines if fuzzy_in("travelling to", l.text) or fuzzy_in("traveling to", l.text)),
                  None)
    if anchor is None:
        return ""
    below = sorted((l for l in lines if l.y > anchor.y + anchor.h * 0.5 and l.y < anchor.y + anchor.h * 7
                    and abs(l.x - anchor.x) < width * 0.08 and sum(c.isalpha() for c in l.text) >= 3
                    and not any(w in l.text.lower() for w in ("weather", "tip", "travel"))),
                   key=lambda l: l.y)
    return " ".join(l.text.strip(" .:-") for l in below[:2]).strip()


def map_parts(raw: str) -> tuple[str, str]:
    """("Fiend City", "Summer Hunt") from a title as read."""
    return split_map(raw)


def recording_key(map_name: str, kind: str = "") -> str:
    return slugify(f"{map_name} {kind}".strip()) if map_name else ""


def label(map_name: str, kind: str = "") -> str:
    return f"{map_name} ({kind})" if kind else map_name


# --- recordings on disk -----------------------------------------------------------
@dataclass
class Recording:
    map: str
    kind: str = ""
    mode: str = ""
    created: str = ""
    result: str = ""                # "win" / "loss" / ""
    waves: int = 0                  # the last wave seen
    events: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return recording_key(self.map, self.kind)

    @property
    def label(self) -> str:
        return label(self.map, self.kind)

    def save(self, folder: Path | None = None) -> Path:
        folder = folder or RECORDINGS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.key}.json"
        path.write_text(json.dumps(asdict(self), separators=(",", ":")), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Recording | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names = cls.__dataclass_fields__
            return cls(**{k: v for k, v in data.items() if k in names})
        except (OSError, ValueError, TypeError):
            return None


def all_recordings(folder: Path | None = None) -> list[Recording]:
    folder = folder or RECORDINGS_DIR
    found = [Recording.load(p) for p in sorted(folder.glob("*.json"))] if folder.exists() else []
    return [r for r in found if r is not None]


def find_any_recording(folder: Path | None = None) -> bool:
    folder = folder or RECORDINGS_DIR
    return folder.exists() and any(folder.glob("*.json"))


def find_recording(key: str = "", map_title: str = "", folder: Path | None = None) -> Recording | None:
    """The recording for this map: by key (from the loading screen), else by
    the map read during the match (the only recording of that map)."""
    folder = folder or RECORDINGS_DIR
    if key and (folder / f"{key}.json").exists():
        return Recording.load(folder / f"{key}.json")
    if map_title:
        name, kind = map_parts(map_title)
        exact = folder / f"{recording_key(name, kind)}.json"
        if name and exact.exists():
            return Recording.load(exact)
        same = [r for r in all_recordings(folder) if name and r.map == name]
        if len(same) == 1:
            return same[0]
    return None


def delete_recording(key: str, folder: Path | None = None) -> None:
    ((folder or RECORDINGS_DIR) / f"{key}.json").unlink(missing_ok=True)


# --- time: waves ---------------------------------------------------------------------
class WaveClock:
    """The current wave and when it began. Only goes up, and a new wave counts
    once it's read twice in a row (a jump of more than 3 needs 4 reads), so a
    misread number can't rush things."""

    def __init__(self, now: float):
        self.wave, self.since = 0, now
        self._candidate, self._reads = None, 0

    def note(self, wave, now: float) -> None:
        if not isinstance(wave, int) or wave <= self.wave:
            self._candidate, self._reads = None, 0
            return
        if wave == self._candidate:
            self._reads += 1
        else:
            self._candidate, self._reads = wave, 1
        if self._reads >= (2 if wave - self.wave <= 3 else 4):
            self.wave, self.since = wave, now
            self._candidate, self._reads = None, 0


# --- recording ---------------------------------------------------------------------------
class Timeline:
    """Turns raw input into the saved actions (see the module text)."""

    def __init__(self, now: float):
        self.clock = WaveClock(now)
        self.events: list[dict] = []
        self.keys_down: set[tuple[int, bool]] = set()
        self.buttons_down: dict[str, tuple[float, float]] = {}
        self._move = [0, 0]
        self._move_at = now

    def note_wave(self, wave, now: float) -> None:
        self.clock.note(wave, now)

    def _push(self, now: float, **event) -> None:
        if event["type"] != "move":
            self._flush_move(now)
        event["wave"] = self.clock.wave
        event["t"] = round(now - self.clock.since, 3)
        self.events.append(event)

    def _flush_move(self, now: float) -> None:
        dx, dy = self._move
        if dx or dy:
            self._move = [0, 0]
            self._push(now, type="move", dx=dx, dy=dy)
        self._move_at = now

    def add(self, event: tuple, now: float, inside: bool, pos: tuple[float, float] | None) -> None:
        """inside: Roblox is in front and a match screen is up; pos: the mouse
        as a fraction of the window (None = outside it)."""
        kind = event[0]
        if kind == "key":
            _, scan, extended, down = event
            ident = (scan, extended)
            if not down:
                if ident in self.keys_down:
                    self.keys_down.discard(ident)
                    self._push(now, type="key", scan=scan, ext=extended, down=False)
                return
            if not inside or ident in self.keys_down or scan in SKIP_SCANS and not extended \
                    or extended and scan in SKIP_EXTENDED:
                return
            if scan == TAB and (ALT, False) in self.keys_down:
                return
            self.keys_down.add(ident)
            self._push(now, type="key", scan=scan, ext=extended, down=True)
        elif kind == "button":
            _, button, down = event
            if down:
                if not inside or pos is None or button in self.buttons_down:
                    return
                self.buttons_down[button] = pos
                self._push(now, type="button", button=button, down=True, x=round(pos[0], 4), y=round(pos[1], 4))
            elif button in self.buttons_down:
                where = self.buttons_down.pop(button)
                self._push(now, type="button", button=button, down=False,
                           x=round(where[0], 4), y=round(where[1], 4))
        elif kind == "wheel":
            if inside and pos is not None:
                self._push(now, type="wheel", delta=event[1], x=round(pos[0], 4), y=round(pos[1], 4))
        elif kind == "move":
            if "right" in self.buttons_down:
                self._move[0] += event[1]
                self._move[1] += event[2]
                if now - self._move_at >= MOVE_EVERY:
                    self._flush_move(now)

    def finish(self, now: float) -> list[dict]:
        """Let go of whatever is still held; → the actions."""
        self._flush_move(now)
        for scan, extended in sorted(self.keys_down):
            self._push(now, type="key", scan=scan, ext=extended, down=False)
        for button, where in list(self.buttons_down.items()):
            self._push(now, type="button", button=button, down=False, x=where[0], y=where[1])
        self.keys_down.clear()
        self.buttons_down.clear()
        return self.events


_user32 = ctypes.WinDLL("user32", use_last_error=True)


def cursor_in(hwnd: int) -> tuple[float, float] | None:
    """The mouse as a fraction of the window's inside, or None if it's outside."""
    point, rect = wintypes.POINT(), wintypes.RECT()
    if not (_user32.GetCursorPos(ctypes.byref(point)) and _user32.ScreenToClient(hwnd, ctypes.byref(point))
            and _user32.GetClientRect(hwnd, ctypes.byref(rect))) or rect.right <= 0 or rect.bottom <= 0:
        return None
    x, y = point.x / rect.right, point.y / rect.bottom
    return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None


class InputRecorder(QThread):
    """Records while running; read `.events` after it has finished."""
    failed = Signal(str)

    def __init__(self, hwnd, screen, wave, source=None, clock=time.monotonic, parent=None):
        super().__init__(parent)
        self._hwnd, self._screen, self._wave = hwnd, screen, wave
        self._source, self._clock = source, clock
        self.events: list[dict] = []
        self.last_wave = 0

    def run(self) -> None:
        source = self._source or RawInput()
        if not source.open():
            self.failed.emit("Couldn't read the keyboard and mouse — recording stopped.")
            return
        timeline = Timeline(self._clock())
        try:
            while not self.isInterruptionRequested():
                now = self._clock()
                timeline.note_wave(self._wave(), now)
                hwnd = self._hwnd()
                front = bool(hwnd) and _user32.GetForegroundWindow() == hwnd
                inside = front and self._screen() in RECORD_SCREENS
                pos = cursor_in(hwnd) if front else None
                for event in source.events():
                    timeline.add(event, now, inside, pos)
                time.sleep(0.005)
        finally:
            self.events = timeline.finish(self._clock())
            self.last_wave = timeline.clock.wave
            source.close()


# --- playing -------------------------------------------------------------------------------
class Player:
    """Hands out the recorded actions as their wave and time come."""

    def __init__(self, events: list[dict], now: float):
        self.events = events
        self.index = 0
        self.clock = WaveClock(now)

    @property
    def done(self) -> bool:
        return self.index >= len(self.events)

    def note_wave(self, wave, now: float) -> None:
        self.clock.note(wave, now)

    def seconds_to_next(self, now: float) -> float | None:
        """0 = due now; None = done, or waiting for a later wave."""
        if self.done:
            return None
        event = self.events[self.index]
        if event["wave"] < self.clock.wave:
            return 0.0                          # this run is ahead: catch up
        if event["wave"] > self.clock.wave:
            return None
        return max(0.0, event["t"] - (now - self.clock.since))

    def pop(self) -> dict:
        event = self.events[self.index]
        self.index += 1
        return event


@functools.lru_cache(maxsize=None)
def with_play_replay(cls):
    """`cls` with your recording played instead of its own placing / upgrading
    on recorded maps, and hands off during the match while you record."""

    class Replaying(cls):
        replay_enabled = False      # Settings → Your own play (set by the Main page)
        replay_key = ""             # the map read off the loading screen (Main page)
        recording_now = False       # you're recording this match: MAACRO keeps its hands off

        def run(self) -> None:
            try:
                super().run()
            finally:
                self._release_replay()

        def _new_match(self) -> None:
            super()._new_match()
            self._release_replay()
            self._player = None
            self._replay_checked = False
            self._match_seen_at = None

        def _release_replay(self) -> None:
            for button in getattr(self, "_held_buttons", set()):
                inp.mouse_button(button, False)
            for scan, extended in getattr(self, "_held_keys", set()):
                inp.scan_key(scan, extended, False)
            self._held_buttons, self._held_keys = set(), set()

        def _replay_player(self) -> Player | None:
            if not self.replay_enabled:
                return None
            if getattr(self, "_replay_checked", False):
                return getattr(self, "_player", None)
            now = time.monotonic()
            if getattr(self, "_match_seen_at", None) is None:
                self._match_seen_at = now
            title = self.detector.tracker.map_name or ""
            if not (self.replay_key or title) and now - self._match_seen_at < MAP_WAIT:
                return "wait"       # the map isn't read yet: don't start placing on our own
            self._replay_checked = True
            recording = find_recording(self.replay_key, title)
            if recording is None or not recording.events:
                return None
            self._player = Player(recording.events, now)
            self._player.note_wave(self.detector.tracker.wave, now)
            self.log.emit(f"Playing your recording of {recording.label} ({len(recording.events)} "
                          "actions, by wave).", "Info")
            return self._player

        def _on_in_match(self, hwnd: int) -> None:
            if self.recording_now:
                self._say("Recording your play — MAACRO keeps its hands off", log=False)
                return
            player = self._replay_player()
            if player == "wait":
                self._say("Reading the map…", log=False)
                return
            if player is None:
                super()._on_in_match(hwnd)
                return
            self._replay_step(hwnd, player)

        def _on_unit_manager(self, hwnd: int) -> None:
            if self.recording_now:
                return
            player = getattr(self, "_player", None) if getattr(self, "_replay_checked", False) else None
            if player is None:
                super()._on_unit_manager(hwnd)
                return
            self._replay_step(hwnd, player)

        def _replay_step(self, hwnd: int, player: Player) -> None:
            if not hasattr(self, "_held_keys"):
                self._held_buttons, self._held_keys = set(), set()
            if player.done:
                self._say("Your recording is done — waiting for the match to end", log=False)
                return
            _, frame = self.capture.latest_frame()
            if frame is None:
                return
            height, width = frame.shape[:2]
            inp.focus(hwnd)
            budget = time.monotonic() + 1.0
            while time.monotonic() < budget and not self.isInterruptionRequested():
                now = time.monotonic()
                player.note_wave(self.detector.tracker.wave, now)
                wait = player.seconds_to_next(now)
                if wait is None or wait > 0.3:
                    break
                if wait > 0:
                    inp.precise_sleep(wait)
                    continue
                self._perform(hwnd, player.pop(), width, height)
            self._say(f"Playing your recording — wave {player.clock.wave}, "
                      f"{player.index}/{len(player.events)} actions", log=False)

        def _perform(self, hwnd: int, event: dict, width: int, height: int) -> None:
            kind = event.get("type")
            if kind == "key":
                ident = (int(event["scan"]), bool(event.get("ext")))
                inp.scan_key(ident[0], ident[1], bool(event["down"]))
                (self._held_keys.add if event["down"] else self._held_keys.discard)(ident)
            elif kind == "button":
                button = event["button"]
                if event["down"]:
                    inp.move_to(hwnd, event["x"] * width, event["y"] * height)
                inp.mouse_button(button, bool(event["down"]))
                (self._held_buttons.add if event["down"] else self._held_buttons.discard)(button)
            elif kind == "wheel":
                inp.move_to(hwnd, event["x"] * width, event["y"] * height)
                inp.wheel(int(event["delta"]))
            elif kind == "move":
                inp.move_by(int(event["dx"]), int(event["dy"]))

    Replaying.__name__ = Replaying.__qualname__ = cls.__name__
    return Replaying


def new_recording(map_title: str, mode: str, events: list[dict], result: str, waves: int) -> Recording:
    name, kind = map_parts(map_title)
    return Recording(map=name or "Unknown map", kind=kind, mode=mode,
                     created=datetime.now().strftime("%Y-%m-%d %H:%M"), result=result, waves=waves,
                     events=events)
