"""Turn the stream of screen detections into steady state and one-off events.

- A screen only counts once it's seen on 2 checks in a row (so one bad read
  doesn't flip the status). "Unknown" needs 6 in a row, because mid-match
  frames often have no readable text.
- A win or loss is counted once per end screen, when 2 reads agree.
"""
from __future__ import annotations

from collections import Counter

from .vision.screens import Detection

CONFIRM = 2
CONFIRM_UNKNOWN = 6
# Seeing one of these means the previous match is over and done with.
FRESH_SCREENS = {"lobby", "join_matchmaking", "captcha", "match_found", "vote_start", "in_match"}


class GameTracker:
    def __init__(self) -> None:
        self.screen = "unknown"
        self.wave: int | None = None
        self.map_name: str | None = None
        self._candidate = "unknown"
        self._streak = 0
        self._end_reads: Counter[str] = Counter()
        self._map_reads: Counter[str] = Counter()
        self._result_counted = False

    def feed(self, det: Detection) -> list[tuple[str, object]]:
        """Take one detection; return events like ("screen", "lobby") or ("result", "win")."""
        events: list[tuple[str, object]] = []

        if det.screen == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = det.screen, 1
        needed = CONFIRM_UNKNOWN if det.screen == "unknown" else CONFIRM
        if self._streak >= needed and det.screen != self.screen:
            self.screen = det.screen
            events.append(("screen", self.screen))
            if self.screen in FRESH_SCREENS:
                self._end_reads.clear()
                self._result_counted = False
            if self.screen in ("lobby", "match_found", "vote_start", "loading", "after_end"):
                self._set_wave(None, events)
                self._map_reads.clear()

        if det.wave is not None and det.screen in ("in_match", "card_pick", "unit_manager", "end"):
            self._set_wave(det.wave, events)
        if det.map_name:
            # Settle on the most common reading so misreads don't flicker.
            self._map_reads[det.map_name] += 1
            name, count = self._map_reads.most_common(1)[0]
            if count >= 3 and name != self.map_name:
                self.map_name = name
                events.append(("map", name))

        # End-screen reads only count while they come in a row, and the result is
        # only counted once the end screen is the steady screen.
        if det.screen != "end":
            self._end_reads.clear()
        elif det.result and not self._result_counted:
            self._end_reads[det.result] += 1
            result, votes = self._end_reads.most_common(1)[0]
            if votes >= CONFIRM and self.screen == "end":
                self._result_counted = True
                events.append(("result", result))
        return events

    def _set_wave(self, wave: int | None, events: list) -> None:
        if wave != self.wave:
            self.wave = wave
            events.append(("wave", wave))
