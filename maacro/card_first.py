"""Card picks come before upgrading, even with the unit manager open.

While upgrading, MacroThread closes the unit manager every 5 s to look for a
card pick behind it, then opens it again. It used to take the first screen
read after closing: when the cards weren't recognised yet in that read, it
pressed F again and the manager covered the cards (seen in the logs as
"Card pick" → "Unit manager" with no pick, twice in a row at wave 9).

CardFirst is a mixin for MacroThread and its subclasses (first in the bases;
macro.py isn't changed):

- the peek watches every read for up to PEEK_WINDOW s after closing (not
  just the first) before it opens the manager again;
- if a card pick was seen in the last RECENT_CARD s and hasn't been voted
  on, the unit manager is closed straight away instead of upgrading.
"""
from __future__ import annotations

import time

from .control import input as inp
from .macro import MacroThread

PEEK_WINDOW = 2.5      # s to watch for the card pick after closing the manager
PEEK_CLEAR_READS = 4   # this many fresh reads with no card pick = nothing there
RECENT_CARD = 6.0      # s a card pick sighting counts as "still waiting to be picked"


class CardFirst:
    _card_voted_at = 0.0
    _uncovered_for = None

    def _on_card_pick(self, hwnd: int) -> None:
        super()._on_card_pick(hwnd)
        if self.match.card_voted:
            self._card_voted_at = time.monotonic()

    def _card_waiting(self) -> bool:
        """A card pick was seen moments ago and hasn't been voted on."""
        seen = getattr(self.match, "card_seen_at", 0.0) or 0.0
        return (self.settings.auto_card_pick and seen > self._card_voted_at
                and time.monotonic() - seen < RECENT_CARD)

    def _on_unit_manager(self, hwnd: int) -> None:
        if self._card_waiting():
            # Once per sighting: F toggles, so pressing it again would reopen it.
            if self._uncovered_for != self.match.card_seen_at:
                self._uncovered_for = self.match.card_seen_at
                self.log.emit("Card pick under the unit manager — closing it to pick first.", "Info")
                inp.press(hwnd, "f")
                self._last_done["card_peek"] = time.monotonic()
            return
        super()._on_unit_manager(hwnd)

    def _peek_for_card_pick(self, hwnd: int) -> bool:
        if not self.settings.auto_card_pick:
            return False
        if not self._cooldown("card_peek", 5.0):
            return False
        inp.press(hwnd, "f")            # F toggles the manager: close
        closed_at = time.monotonic()
        start_reads = self.detector.latest_count
        self.msleep(250)
        seen_reads = 0
        while time.monotonic() - closed_at < PEEK_WINDOW:
            if self.isInterruptionRequested():
                return True
            det = self.detector.latest
            fresh = self.detector.latest_count - start_reads
            if det is not None and self.detector.latest_time > closed_at + 0.12:
                if det.screen == "card_pick":
                    self.match.card_seen_at = time.monotonic()
                    self.log.emit("Card pick behind the unit manager — picking first.", "Info")
                    return True
                seen_reads = fresh
                if seen_reads >= PEEK_CLEAR_READS:
                    break
            self.msleep(40)
        inp.press(hwnd, "f")            # nothing: open it again
        self._manager_seen_at = time.monotonic()
        self.msleep(300)
        return True


from .place_only import PlaceOnlyUnits  # noqa: E402


class SummerThread(CardFirst, PlaceOnlyUnits, MacroThread):
    """Summer Event: MacroThread with card picks first and place-only units."""
