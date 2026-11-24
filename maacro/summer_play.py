"""Summer Event: the lobby's Play button now opens "Where do you want to
Play?" (Summer Event / Misty Village / Regular Stages) instead of teleporting
(UPD 21.5, seen live: MAACRO clicked Play, the window opened, and it said
"Play click didn't register" forever). Pick the Summer Event tile there, then
the original flow goes on (walk to the matchmaking ring). macro.py stays as it
was: this only overrides click_play.
"""
from __future__ import annotations

import time

from .control import input as inp
from .lobby_start import PLAY_SPOT, chooser_tile, find_word
from .vision.ocr import OcrLine

HEADER = "where do you want to play"
SUMMER_TILE = "summer event"
CHOOSER_OPENS = 4.0     # s after the Play click for the window to show


class SummerPlayTile:
    """Mixin for SummerThread (put before MacroThread)."""

    def _chooser_header(self, lines) -> OcrLine | None:
        return find_word(lines, HEADER, threshold=0.7)

    def _next_detection(self, after: float, timeout: float, test):
        """The first detection of a frame taken after `after` for which
        test(det) is truthy, or None after `timeout` s."""
        end = time.monotonic() + timeout
        seen = -1
        while time.monotonic() < end:
            if self.isInterruptionRequested():
                return None
            count, det = self.detector.latest_count, self.detector.latest
            if count != seen and det is not None and self.detector.latest_time > after + 0.12:
                seen = count
                found = test(det)
                if found:
                    return found
            self.msleep(30)
        return None

    def click_play(self, hwnd: int, det=None) -> bool:
        det = det or self.detector.latest
        if det is None:
            return False
        header = self._chooser_header(det.lines)
        if header is None:
            play = self._line(det, "play", exact=True)
            clicked_at = time.monotonic()
            if play is not None:
                self._say("In lobby → clicking Play")
                self._click_line(hwnd, play, "Play")
            else:
                width, height = window_size(self)
                self._say("In lobby → clicking Play (its usual place — the text wasn't read)")
                inp.focus(hwnd)
                inp.click(hwnd, PLAY_SPOT[0] * width, PLAY_SPOT[1] * height)
            # The chooser should open; if the game teleports instead (the old
            # way), that's fine too.
            result = self._next_detection(
                clicked_at, CHOOSER_OPENS,
                lambda d: ("header", d) if self._chooser_header(d.lines)
                else ("left", d) if d.screen != "lobby" else None)
            if result is None:
                if not self.isInterruptionRequested():
                    self.log.emit("Play click didn't open the 'Where do you want to Play?' window — "
                                  "clicking again.", "Warn")
                return False
            kind, det = result
            if kind == "left":
                return self._left_lobby(clicked_at, timeout=self.settings.teleport_wait + 3)
            header = self._chooser_header(det.lines)
        tile = chooser_tile(det.lines, SUMMER_TILE, header)
        self._say("Play window → clicking Summer Event")
        clicked_at = time.monotonic()
        self._click_line(hwnd, tile, "Summer Event")
        if self._left_lobby(clicked_at, timeout=self.settings.teleport_wait + 3):
            return True
        if not self.isInterruptionRequested():
            self.log.emit("Summer Event click didn't teleport — trying again.", "Warn")
        return False


def window_size(thread) -> tuple[int, int]:
    """The window's size in pixels (from the newest frame)."""
    _, frame = thread.capture.latest_frame()
    if frame is not None:
        return frame.shape[1], frame.shape[0]
    return 1920, 991
