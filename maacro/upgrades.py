"""Upgrading more than 6 units: the Unit Overview's pages.

The unit manager ("Unit Overview") shows 6 units per page, with a ">" arrow
on its right edge for the next page. Summer's upgrade step only ever sees
the page that's open, so a 7th unit and later never get upgraded.

PagedUpgrades is a mixin for MacroThread subclasses (like PartyMemberBehavior,
it goes first in the bases). It leaves the upgrading itself to MacroThread
(the same tested clicks, in upgrade-priority order) and only turns the pages:

- a page with upgrade buttons is upgraded for up to PAGE_STAY seconds, then
  the next page gets its turn (so one page's units can't starve the others);
- a page with nothing to upgrade is turned straight away;
- once every page has come up empty in a row, MacroThread decides "all
  maxed" as before (and checks again later).

It goes ">" to the last page, then "<" back. If "<" can't be found, closing
the manager (F) and opening it again starts from page 1. With 6 units or
fewer there's no arrow and nothing changes.

macro.py isn't changed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from .control import input as inp
from .placement import find_green_buttons
from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

# The ">" arrow's centre from the "Unit Overview" title's centre, × the
# title's width (measured on screens/20_unit_overview_live.png: title 318 px
# wide at x 1426, arrow at 1833, 354). "<" is assumed mirrored on the left.
ARROW_DX, ARROW_DY = 0.78, 0.80
ARROW_SEARCH = 0.12          # search box half-size around it, × title width
PAGE_STAY = 10.0             # s on a page that still has upgrades, then the next page
EMPTY_FLIP = 1.5             # s on a page with nothing to upgrade
SETTLE = 0.6                 # s after turning a page before reading it


def overview_title(lines: list[OcrLine]) -> OcrLine | None:
    for line in lines:
        if fuzzy_in("unit overview", line.text, 0.75):
            return line
    return None


def find_page_arrow(frame: np.ndarray, title: OcrLine, direction: str) -> tuple[float, float] | None:
    """Centre of the Unit Overview's ">" (or "<") arrow, or None if it's not
    there (one page only, or already on the last / first page)."""
    height, width = frame.shape[:2]
    sign = 1 if direction == ">" else -1
    cx, cy = title.center_x + sign * ARROW_DX * title.w, title.y + title.h / 2 + ARROW_DY * title.w
    half = ARROW_SEARCH * title.w
    x0, x1 = int(max(0, cx - half)), int(min(width, cx + half))
    y0, y1 = int(max(0, cy - half)), int(min(height, cy + half))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1, :3]), cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 2] > 215) & (hsv[..., 1] < 70)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white)
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        # A chevron: taller than wide, about 0.08 × 0.11 title widths, not a solid block.
        if not (0.04 * title.w < w < 0.13 * title.w and 0.07 * title.w < h < 0.18 * title.w):
            continue
        if h < 1.1 * w or area > 0.75 * w * h:
            continue
        ys, xs = np.nonzero(labels[y:y + h, x:x + w] == i)
        middle = np.abs(ys - h / 2) < h / 6
        ends = np.abs(ys - h / 2) > h / 3
        if not middle.any() or not ends.any():
            continue
        # ">" sticks out to the right in the middle; "<" to the left.
        points_right = xs[middle].mean() > xs[ends].mean()
        if points_right == (direction == ">"):
            return x0 + x + w / 2, y0 + y + h / 2
    return None


@dataclass
class PageState:
    page: int = 1
    step: int = 1                 # +1 going ">", -1 going "<"
    paged: bool = False           # seen more than one page this match
    since: float = 0.0            # when this page came up
    empty_run: int = 0            # pages in a row turned with nothing to upgrade
    pages_seen: int = 1
    done_at: float = 0.0          # MacroThread's last "all maxed" time seen


class PagedUpgrades:
    """Mixin: upgrade units on every Unit Overview page, not just the first."""

    def _new_match(self) -> None:
        super()._new_match()
        self._pages = PageState(since=time.monotonic())

    def _page_state(self) -> PageState:
        if getattr(self, "_pages", None) is None:
            self._pages = PageState(since=time.monotonic())
        return self._pages

    def _on_unit_manager(self, hwnd: int) -> None:
        m, cfg = self.match, self.settings
        st = self._page_state()
        if m.upgrades_done_at != st.done_at:        # a fresh look after "all maxed"
            st.done_at, st.empty_run = m.upgrades_done_at, 0
        upgrading = cfg.upgrade_units and not m.upgrades_done and not (
            cfg.place_units and m.pending and not self._place_paused())
        det = self.detector.latest
        _, frame = self.capture.latest_frame()
        if not upgrading or det is None or frame is None or det.screen != "unit_manager":
            super()._on_unit_manager(hwnd)
            return
        now = time.monotonic()
        title = overview_title(det.lines)
        nxt = find_page_arrow(frame, title, ">") if title is not None else None
        prev = find_page_arrow(frame, title, "<") if title is not None else None
        if nxt is not None or prev is not None:
            st.paged = True
        if not st.paged:
            super()._on_unit_manager(hwnd)          # one page: nothing changes
            return
        if now - st.since < SETTLE:
            return                                  # the page is still turning
        has_work = bool(find_green_buttons(frame)) or any(
            _norm(l.text).startswith("upg") for l in det.lines)
        if has_work:
            st.empty_run = 0
        if not has_work and st.empty_run >= 2 * max(2, st.pages_seen):
            # Every page came up empty: let MacroThread decide "all maxed".
            super()._on_unit_manager(hwnd)
            return
        stay = PAGE_STAY if has_work else EMPTY_FLIP
        if now - st.since < stay:
            if has_work:
                super()._on_unit_manager(hwnd)      # upgrade this page
            return
        if not has_work:
            st.empty_run += 1                       # counted once per page
        self._turn_page(hwnd, st, nxt, prev)

    def _turn_page(self, hwnd: int, st: PageState, nxt, prev) -> None:
        if st.step > 0 and nxt is None:
            st.step = -1
        elif st.step < 0 and prev is None:
            st.step = 1
        target = nxt if st.step > 0 else prev
        st.since = time.monotonic()
        self.match.no_upgrade_reads = 0
        if target is None:
            # Last page and no "<" found: close the manager; it opens on page 1.
            self._say("Upgrading — back to page 1 (closing the unit manager)", log=False)
            st.page, st.step = 1, 1
            inp.press(hwnd, "f")
            return
        st.page = max(1, st.page + st.step)
        st.pages_seen = max(st.pages_seen, st.page)
        self._say(f"Upgrading — Unit Overview page {st.page}", log=False)
        inp.click(hwnd, *target)
        self._park_mouse(hwnd)
