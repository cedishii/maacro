"""Upgrading more than 6 units: scrolling the Unit Overview.

The unit manager ("Unit Overview") shows about 6 units; the rest are further
down its list, which scrolls with the mouse wheel. Summer's upgrade step only
sees what's on screen, so a 7th unit and later never get upgraded.

ScrollingUpgrades is a mixin for MacroThread subclasses (like
PartyMemberBehavior, it goes first in the bases). The upgrading itself is
still MacroThread's (the same tested clicks, in upgrade-priority order); this
only moves the list:

- a part of the list with upgrade buttons is upgraded for up to STAY
  seconds, then the list scrolls on (so the top units can't starve the rest);
- a part with nothing to upgrade is scrolled past straight away;
- when the list doesn't move any more it's at the bottom: back to the top;
- once the whole list has come up empty in a row, MacroThread decides "all
  maxed" as before (and checks again later).

Whether the list moved is told from the "First" buttons (one per unit card):
the same positions before and after a scroll = nothing more to see. A list
that never moves (6 units or fewer) is left alone, and looked at again
every REPROBE seconds in case more units went down.

The wheel is only used with the "Unit Overview" title read, on the cards
below it (over the game world it would zoom the camera). macro.py isn't
changed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .control import input as inp
from .placement import find_green_buttons
from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

# Where the wheel goes: the middle of the unit cards, from the "Unit Overview"
# title's centre (× the title's width; measured on screens/20_unit_overview_live.png:
# title 318 px wide at 1426, 82; the cards fill y 150–720 below it).
LIST_DY = 0.95
SCROLL_NOTCHES = 3          # per step down
TOP_NOTCHES = 30            # back to the top in one go
STAY = 10.0                 # s on a part of the list that still has upgrades
EMPTY_STAY = 1.5            # s on a part with nothing to upgrade
SETTLE = 0.7                # s after scrolling before reading the list again
REPROBE = 60.0              # s before checking a list that didn't scroll again
MOVED = 6                   # px a "First" button must shift to count as scrolled
MAX_STEPS = 15              # never more steps down than this before going back to the top


def overview_title(lines: list[OcrLine]) -> OcrLine | None:
    for line in lines:
        if fuzzy_in("unit overview", line.text, 0.75):
            return line
    return None


def card_marks(lines: list[OcrLine], title: OcrLine) -> tuple[list, list]:
    """What tells one part of the list from another: the cards' "First"
    buttons (positions) and the unit names on screen (a scroll of exactly one
    row puts First buttons back in the same places, but not the same names)."""
    inside = [l for l in lines if l.x > title.x - 0.6 * title.w and l.y > title.y + title.h]
    firsts = sorted((l.center_x, l.y) for l in inside if _norm(l.text) == "first")
    names = sorted(_norm(l.text) for l in inside
                   if not any(c.isdigit() for c in l.text) and len(_norm(l.text)) >= 3
                   and _norm(l.text) not in ("first", "max") and not _norm(l.text).startswith("upg"))
    return firsts, names


def list_moved(before, after) -> bool:
    (b, b_names), (a, a_names) = before, after
    if b_names != a_names:
        return True
    if not b or not a:
        return bool(b) != bool(a)
    if len(b) != len(a):
        return True
    return any(abs(p[1] - q[1]) > MOVED or abs(p[0] - q[0]) > MOVED for p, q in zip(b, a))


@dataclass
class ScrollState:
    scrollable: bool | None = None  # None = not tried yet
    probed_at: float = 0.0
    since: float = 0.0              # when this part of the list came up
    steps: int = 0                  # scroll steps below the top
    most_steps: int = 0
    empty_run: int = 0              # parts in a row with nothing to upgrade
    before: tuple = ([], [])        # card marks before the last scroll
    checking: bool = False          # the last scroll's result isn't read yet
    reads: int = 0                  # detector reads when it scrolled
    done_at: float = 0.0            # MacroThread's last "all maxed" time seen


class ScrollingUpgrades:
    """Mixin: upgrade every unit in the Unit Overview, not just the first 6."""

    def _new_match(self) -> None:
        super()._new_match()
        self._scroll = ScrollState(since=time.monotonic())

    def _scroll_state(self) -> ScrollState:
        if getattr(self, "_scroll", None) is None:
            self._scroll = ScrollState(since=time.monotonic())
        return self._scroll

    def _on_unit_manager(self, hwnd: int) -> None:
        m, cfg = self.match, self.settings
        st = self._scroll_state()
        if m.upgrades_done_at != st.done_at:        # a fresh look after "all maxed"
            st.done_at, st.empty_run = m.upgrades_done_at, 0
        upgrading = cfg.upgrade_units and not m.upgrades_done and not (
            cfg.place_units and m.pending and not self._place_paused())
        det = self.detector.latest
        title = overview_title(det.lines) if det is not None and det.screen == "unit_manager" else None
        if not upgrading or title is None:
            st.checking = False
            super()._on_unit_manager(hwnd)
            return
        now = time.monotonic()
        if st.checking:
            fresh = getattr(self.detector, "latest_count", 0) >= st.reads + 2
            if now - st.since < SETTLE or (not fresh and now - st.since < 5):
                return                              # still scrolling / not read since
            st.checking = False
            if not list_moved(st.before, card_marks(det.lines, title)) or st.steps >= MAX_STEPS:
                if st.steps == 0:
                    st.scrollable, st.probed_at = False, now     # nothing below: leave it
                else:
                    self._scroll_to_top(hwnd, title)             # at the bottom
                    return
            else:
                st.scrollable = True
                st.steps += 1
                st.most_steps = max(st.most_steps, st.steps)
        if st.scrollable is False:
            if now - st.probed_at < REPROBE:
                super()._on_unit_manager(hwnd)      # one screenful: nothing changes
                return
            st.scrollable = None                    # more units may have gone down
        _, frame = self.capture.latest_frame()
        has_work = (frame is not None and bool(find_green_buttons(frame))) or any(
            _norm(l.text).startswith("upg") for l in det.lines)
        if has_work:
            st.empty_run = 0
        elif st.scrollable and st.empty_run >= max(3, st.most_steps + 2):
            # The whole list came up empty: let MacroThread decide "all maxed".
            super()._on_unit_manager(hwnd)
            return
        if now - st.since < (STAY if has_work else EMPTY_STAY):
            if has_work:
                super()._on_unit_manager(hwnd)      # upgrade what's on screen
            return
        if not has_work:
            st.empty_run += 1                       # counted once per part of the list
        self._scroll_down(hwnd, title, det.lines)

    def _list_spot(self, title: OcrLine) -> tuple[float, float]:
        return title.center_x, title.y + title.h / 2 + LIST_DY * title.w

    def _scroll_down(self, hwnd: int, title: OcrLine, lines: list[OcrLine]) -> None:
        st = self._scroll
        st.before = card_marks(lines, title)
        st.checking, st.since = True, time.monotonic()
        st.reads = getattr(self.detector, "latest_count", 0)
        self.match.no_upgrade_reads = 0
        self._say("Upgrading — scrolling the unit list down", log=False)
        inp.scroll(hwnd, *self._list_spot(title), SCROLL_NOTCHES)
        self._park_mouse(hwnd)

    def _scroll_to_top(self, hwnd: int, title: OcrLine) -> None:
        st = self._scroll
        st.steps, st.since = 0, time.monotonic()
        self.match.no_upgrade_reads = 0
        self._say("Upgrading — back to the top of the unit list", log=False)
        inp.scroll(hwnd, *self._list_spot(title), -TOP_NOTCHES)
        self._park_mouse(hwnd)
