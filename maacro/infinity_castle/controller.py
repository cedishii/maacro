"""The Infinity Castle controller.

Room loop (the player starts it inside Infinity Mansion):
    vote start → place + upgrade → Victory/Defeat → Next
    → "Return to lobby | Next Room" (or "| Retry" after a defeat)
    → press Next Room / Retry (never Return to lobby) → travelling → repeat.

It's a subclass of Summer's MacroThread, so placing, upgrading, closing
popups, Reconnect and the stuck-screen watchdog are the same tested code.
Only the steps that differ are replaced here; macro.py isn't changed.
The lobby, Play, ring walk, matchmaking and captcha steps are switched off.
"""
from __future__ import annotations

import re
import time
import winsound

from PySide6.QtCore import Signal

from ..control import input as inp
from ..macro import MacroThread
from ..vision.screens import Detection, _norm, fuzzy_in
from .config import InfinityConfig
from .maps import load_ic_maps

ROOM_RE = re.compile(r"room\W{0,3}(\d{1,4})", re.IGNORECASE)
# Where Next Room / Retry sits on the frame, when no button text is read at
# all (measured on 1527×790 frames; the button is about 15% wide).
CONTINUE_SPOT = (0.578, 0.20)
# ...and relative to the "Return to lobby" text, when only that is read.
CONTINUE_DX = 1.22      # × the text's width, to the right of its centre
FAST_KEYS = {"place": 0.5, "upgrade": 0.5}   # cooldown multipliers with fast_economy
CONTINUE_RETRY = 6      # seconds between Next Room / Retry clicks
CONTINUE_TRIES = 5      # clicks before switching to the fixed spot
ALERT_TRIES = 20        # then beep and ask the player to look
ROOM_OVER_GRACE = 20    # s after a room ends with no loading/vote start: buttons unread → fixed spot


class InfinityCastleThread(MacroThread):
    ALLOW_LOBBY_PLAY = False        # never queue from the lobby
    ALLOW_RETURN_TO_LOBBY = False   # never leave the castle
    # Its own party-level decision (Party Member mode leaves it to the leader).
    PROGRESSION_ACTIONS = ("_continue",)
    progress = Signal(dict)     # {"room", "cleared", "retries", "note"} for the UI

    def __init__(self, capture, detector, settings: InfinityConfig | None = None, parent=None):
        super().__init__(capture, detector, settings or InfinityConfig(), parent)
        self._ic_maps = []
        self._reset_progress()

    def _reset_progress(self) -> None:
        self.room: int | None = None
        self.cleared = 0
        self.retries = 0
        self._continue_tries = 0
        self._lobby_warned = False
        self._room_over_at: float | None = None
        self._room_counted = False      # this room's Victory/Defeat is counted

    def _emit_progress(self, note: str = "") -> None:
        self.progress.emit({"room": self.room, "cleared": self.cleared,
                            "retries": self.retries, "note": note})

    # --- lifecycle -----------------------------------------------------
    def run(self) -> None:
        self._ic_maps = load_ic_maps()
        self._reset_progress()
        names = ", ".join(m.name for m in self._ic_maps) or "none yet"
        self.log.emit(f"Infinity Castle mode — Next Room after a win, Retry after a defeat. "
                      f"Path zones saved for: {names}.", "Info")
        self._emit_progress("Started")
        super().run()

    # --- shared steps, tuned for this mode -------------------------------
    def _cooldown(self, key: str, seconds: float) -> bool:
        if getattr(self.settings, "fast_economy", False) and key in FAST_KEYS:
            seconds *= FAST_KEYS[key]
        return super()._cooldown(key, seconds)

    def _watch_map(self, det: Detection | None) -> None:
        # Recognise maps from this mode's own zones (not Summer's).
        if self._maps is not self._ic_maps:
            self._maps = self._ic_maps
        screen = self.detector.tracker.screen
        # Each room can be a different map, and the castle never goes back to
        # the lobby (where Summer forgets the map): forget it on every new
        # room, so the next one is recognised again (its own zones and walk,
        # or none at all).
        room = self._read_room(det) if det is not None else None
        # (Rooms only go up: a lower number is a misread. The walk itself is
        # reset only by the loading screen, so a misread mid-room can't make
        # it walk away from units it already placed.)
        new_room = room is not None and self.room is not None and room > self.room
        if (screen == "loading" and getattr(self, "_ic_screen", None) != "loading") or new_room:
            if self._map is not None:
                self.log.emit(f"New room — forgetting {self._map.name}'s zones until "
                              "this room's map is recognised.", "Info")
            self._map, self._map_warned = None, False
        self._ic_screen = screen
        super()._watch_map(det)
        if screen in ("end", "after_end"):
            self._room_over_at = self._room_over_at or time.monotonic()
        elif screen in ("loading", "vote_start", "lobby"):
            self._room_over_at = None
            self._room_counted = False
        # Count the room from its end screen (Victory → cleared, Defeat →
        # retried), once: the button that gets pressed later can't tell.
        if (screen == "end" and det is not None and det.screen == "end" and det.result
                and not self._room_counted):
            self._room_counted = True
            if det.result == "win":
                self.cleared += 1
            else:
                self.retries += 1
            self._emit_progress("Victory" if det.result == "win" else "Defeat — will retry")
        if det is not None:
            room = self._read_room(det)
            if room is not None and room != self.room:
                self.room = room
                self.log.emit(f"Infinity Mansion: room {room}.", "Info")
                self._emit_progress()

    @staticmethod
    def _read_room(det: Detection) -> int | None:
        for line in det.lines:
            if "mansion" in line.text.lower() or "room" in line.text.lower():
                match = ROOM_RE.search(line.text)
                if match:
                    return int(match.group(1))
        return None

    def _walk_map(self, hwnd: int, walk: dict, what: str | None = None) -> None:
        """After the map walk, zoom out again: the room's start can reset the
        camera after the first zoom (it stayed close up in room 9)."""
        super()._walk_map(hwnd, walk, what)
        seconds = getattr(self.settings, "zoom_out_seconds", 0)
        if what is None and seconds > 0 and not self.isInterruptionRequested():
            self._say("Zooming out again after the walk (O)")
            inp.press(hwnd, "o", hold=seconds)
            self._sleep(0.5)

    def _place_next(self, hwnd: int) -> None:
        """Damage units (path_units) take the circled path zones; the others
        are placed with the zones hidden, so they don't fill the path spots."""
        m = self.match
        key = m.pending[0] if m.pending else None
        if key is None or key in getattr(self.settings, "path_units", []) or self._map is None:
            super()._place_next(hwnd)
            return
        zones, self._map = self._map, None
        try:
            super()._place_next(hwnd)
        finally:
            self._map = zones

    # --- steps that don't exist in this mode -----------------------------
    def _on_lobby(self, hwnd: int) -> None:
        if not self._lobby_warned:
            self._lobby_warned = True
            self.log.emit("In the lobby — Infinity Castle is paused. Go into Infinity Mansion "
                          "and it carries on by itself (it never queues from the lobby).", "Warn")
            self._emit_progress("Paused: in the lobby")
        self._say("Paused — in the lobby (enter Infinity Mansion)", log=False)

    def _on_join_matchmaking(self, hwnd: int) -> None:
        self._say("Paused — matchmaking isn't used in Infinity Castle", log=False)

    def _on_captcha(self, hwnd: int) -> None:
        self._say("Paused — captcha isn't part of Infinity Castle", log=False)

    # --- room over: Next Room / Retry ------------------------------------
    @staticmethod
    def _pregame(det: Detection) -> bool:
        """The castle's own waiting room ("Game will begin soon…")."""
        return any(fuzzy_in("game will begin", l.text) for l in det.lines)

    def _continue_button(self, det: Detection):
        """(x, y, label) of Next Room or Retry, or None. Read text first, then
        its spot right of "Return to lobby"; never Return to lobby itself."""
        for keyword, label in (("next room", "Next Room"), ("retry", "Retry")):
            line = self._line(det, keyword, exact=(keyword == "retry")) \
                or (self._line(det, keyword) if keyword == "next room" else None)
            if line is not None:
                return line.center_x, line.y + line.h / 2, label
        if self._continue_tries >= CONTINUE_TRIES or any(
                fuzzy_in("return to lobby", l.text) for l in det.lines):
            back = self._line(det, "return to lobby")
            if back is not None:
                return back.center_x + CONTINUE_DX * back.w, back.y + back.h / 2, "Next Room / Retry"
            if self._continue_tries >= CONTINUE_TRIES:
                width, height = self._frame_size()
                return CONTINUE_SPOT[0] * width, CONTINUE_SPOT[1] * height, "Next Room / Retry (usual spot)"
        return None

    def _continue(self, hwnd: int, det: Detection) -> bool:
        """Press Next Room / Retry once (then again every CONTINUE_RETRY s
        while the screen stays). True if this screen was handled here."""
        if self._pregame(det):
            self._say("Waiting in the castle room for the game to start", log=False)
            return True
        if self._close_covering_manager(hwnd, det):
            return True
        target = self._continue_button(det)
        if target is None:
            return False
        if not self._cooldown("ic_continue", CONTINUE_RETRY):
            return True
        x, y, label = target
        self._continue_tries += 1
        if self._continue_tries > 1:
            self.log.emit(f"Still on the room-over screen — pressing {label} again "
                          f"(try {self._continue_tries}).", "Warn")
        if self._continue_tries == ALERT_TRIES:
            self.log.emit(f"Next Room / Retry still hasn't worked after {ALERT_TRIES} tries — "
                          "please check the game (MAACRO keeps trying).", "Error")
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
        self._say(f"Room over → pressing {label}")
        inp.focus(hwnd)
        inp.click(hwnd, x, y)
        self._park_mouse(hwnd)
        if self._continue_tries == 1:
            self._emit_progress(f"Pressed {label}")
        return True

    def _on_after_end(self, hwnd: int) -> None:
        det = self.detector.latest
        if det is not None and det.screen == "after_end":
            self._continue(hwnd, det)

    def _on_in_match(self, hwnd: int) -> None:
        # With "Return to lobby" unread, the room-over screen still shows the
        # wave counter and reads as the match: look for its buttons first.
        det = self.detector.latest
        if det is not None and any(_norm(l.text) in ("nextroom", "retry") for l in det.lines):
            self._continue(hwnd, det)
            return
        # The room ended, yet no loading or vote start came: the room-over
        # screen is up with none of its buttons read (it still shows the wave,
        # so it reads as the match). Press the usual Next Room / Retry spot.
        if det is not None and self._room_over_at is not None                 and time.monotonic() - self._room_over_at > ROOM_OVER_GRACE:
            if self._continue_tries < CONTINUE_TRIES and not getattr(self, "party_member", False):
                self.log.emit("The room is over but its buttons can't be read — "
                              "pressing where Next Room / Retry usually is.", "Warn")
                self._continue_tries = CONTINUE_TRIES
            self._continue(hwnd, det)
            return
        self._continue_tries = 0      # a room is being played: next room-over starts fresh
        super()._on_in_match(hwnd)

    def _on_loading(self, hwnd: int) -> None:
        self._continue_tries = 0
        super()._on_loading(hwnd)

    def _on_vote_start(self, hwnd: int) -> None:
        self._continue_tries = 0
        super()._on_vote_start(hwnd)

    # --- watchdog steps for this mode ------------------------------------
    def _recover(self, hwnd: int, screen: str, step: int) -> str:
        det = self.detector.latest
        if screen == "after_end" and det is not None and self._pregame(det):
            return "still in the castle room, waiting for the game to start"
        if screen == "after_end":
            if det is not None and self._manager_open(det):
                inp.press(hwnd, "f")
                return "closing the unit manager that's covering it"
            self._last_done.pop("ic_continue", None)
            self._continue_tries = max(self._continue_tries, CONTINUE_TRIES)   # allow the fixed spot
            if det is not None and self._continue(hwnd, det):
                return "pressing Next Room / Retry again"
            return "Next Room / Retry not found — waiting"
        if screen in ("lobby", "join_matchmaking", "captcha"):
            return "Infinity Castle is paused here — enter Infinity Mansion"
        return super()._recover(hwnd, screen, step)
