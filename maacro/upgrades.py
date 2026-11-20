"""Upgrading every unit: scrolling the Unit Overview.

The unit manager ("Unit Overview") shows 8 units (4 rows of 2); the rest are further
down its list, which scrolls with the mouse wheel. Summer's upgrade step only
sees what's on screen, so a 9th unit and later never get upgraded.

ScrollingUpgrades is a mixin for MacroThread subclasses (like
PartyMemberBehavior, it goes first in the bases). The upgrading itself is
still MacroThread's (the same tested clicks, in upgrade-priority order); this
only moves the list:

- every sweep starts at the TOP of the list: when the manager is opened
  again, after a unit was placed (new units must be seen), and after a
  "maxed" recheck;
- a part of the list with upgrade buttons is upgraded for up to STAY
  seconds, then the list scrolls on (so the top units can't starve the rest);
- a part with nothing to upgrade is scrolled past straight away;
- when the list doesn't move any more it's at the bottom: back to the top
  (checked: if the list didn't move up, it's tried again);
- once the whole list has come up empty in a row, MacroThread decides "all
  maxed" as before (and checks again later).

Whether the list moved is told first from the picture of the cards (the
portraits, buttons and frames are solid; compared in small blocks with the
brightness evened out, so the game moving behind the panel only changes a
few blocks while a scroll changes most of them). When the picture can't tell,
the text decides: each card's "First" button and the unit name next to it. The panel is see-through, so the game's
own text behind it (enemy counts, buffs…) is read too and changes on every
read — it's left out, or the bottom of the list would never be noticed and
the macro would keep scrolling down. A small misread (one name, one missing
button) doesn't count as a move. A list that never moves (8 units or fewer)
is left alone, and looked at again every REPROBE seconds or after a unit is
placed.

The wheel is only used with the "Unit Overview" title read, on the cards
below it (over the game world it would zoom the camera). macro.py isn't
changed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from difflib import SequenceMatcher

import cv2
import numpy as np

from .control import input as inp
from .placement import find_green_buttons
from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

# Where the wheel goes: the middle of the unit cards, from the "Unit Overview"
# title's centre (× the title's width; measured on screens/20_unit_overview_live.png:
# title 318 px wide at 1426, 82; the cards fill y 150–720 below it).
LIST_DY = 0.95
SCROLL_NOTCHES = 3          # per step down
TOP_NOTCHES = 30            # back to the top in one go (more for a long list)
STAY = 10.0                 # s on a part of the list that still has upgrades
EMPTY_STAY = 1.5            # s on a part with nothing to upgrade
SETTLE = 0.7                # s after scrolling before reading the list again
REPROBE = 30.0              # s before checking a list that didn't scroll again
REOPEN_GAP = 3.0            # s without the manager = it was closed and opened again
MOVED = 6                   # px a "First" button must shift to count as scrolled
MAX_STEPS = 12              # steps down before going back to the top (bottom not found yet)
UP_RETRIES = 2              # tries more when the list didn't go back up


# Picture check: share of blocks that changed. A scroll changes 0.8+ of them
# (one row on screens/20 and ic_03: 0.8 / 0.91), the game behind the panel
# at most ~0.35 (every dark pixel swapped); between the two the text decides.
PICTURE_MOVED = 0.6
PICTURE_SAME = 0.3
SIG_W, SIG_H, BLOCK = 48, 64, 4


def list_signature(frame, title: OcrLine):
    """A small brightness-evened grey picture of the cards under the title."""
    if frame is None:
        return None
    height, width = frame.shape[:2]
    x0, x1 = int(title.x - 0.45 * title.w), int(title.x + 1.45 * title.w)
    y0, y1 = int(title.y + 2 * title.h), int(title.y + title.h + 1.95 * title.w)
    crop = frame[max(0, y0):min(height, y1), max(0, x0):min(width, x1)]
    if crop.shape[0] < SIG_H or crop.shape[1] < SIG_W:
        return None
    grey = cv2.cvtColor(np.ascontiguousarray(crop[..., :3]), cv2.COLOR_BGR2GRAY)
    small = cv2.resize(grey, (SIG_W, SIG_H), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (small - small.mean()) / (small.std() + 1e-3) * 40


def picture_change(before, after) -> float | None:
    """Share of blocks that changed between two signatures (None = can't tell)."""
    if before is None or after is None or before.shape != after.shape:
        return None
    diff = np.abs(before - after).reshape(SIG_H // BLOCK, BLOCK, SIG_W // BLOCK, BLOCK).mean(axis=(1, 3))
    return float((diff > 14).mean())


def overview_title(lines: list[OcrLine]) -> OcrLine | None:
    for line in lines:
        if fuzzy_in("unit overview", line.text, 0.75):
            return line
    return None


def _inside(lines: list[OcrLine], title: OcrLine) -> list[OcrLine]:
    return [l for l in lines if l.x > title.x - 0.6 * title.w and l.y > title.y + title.h]


def _name_like(line: OcrLine) -> bool:
    n = _norm(line.text)
    return (not any(c.isdigit() for c in line.text) and len(n) >= 3
            and n not in ("first", "max") and not n.startswith("upg"))


def card_names(lines: list[OcrLine], title: OcrLine) -> list[str]:
    """Every name-like text under the title (for counting units by name)."""
    return sorted(_norm(l.text) for l in _inside(lines, title) if _name_like(l))


def card_marks(lines: list[OcrLine], title: OcrLine) -> tuple[list, list]:
    """What tells one part of the list from another: each card's "First"
    button (position) and the unit name printed on that card, in the same
    order (a scroll of exactly one row puts the buttons back in the same
    places, but not the same names). Text that isn't on a card — the game
    behind the see-through panel — is left out."""
    inside = _inside(lines, title)
    firsts = sorted((l for l in inside if _norm(l.text) == "first"), key=lambda l: (l.y, l.x))
    names = [l for l in inside if _name_like(l)]
    points, labels = [], []
    for f in firsts:
        # The name sits on the portrait, left of the button, about level with it.
        near = [l for l in names
                if f.x - 4 * f.w <= l.center_x <= f.x and f.y - f.h <= l.y <= f.y + 3 * f.h]
        best = min(near, key=lambda l: abs(l.y - (f.y + f.h)) + 0.3 * abs(l.center_x - (f.x - 1.8 * f.w)),
                   default=None)
        points.append((f.center_x, f.y))
        labels.append(_norm(best.text) if best is not None else "")
    return points, labels


def _same_name(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.85


def _names_differ(before: list[str], after: list[str]) -> bool:
    """Most of the names changed (one misread name doesn't count)."""
    before, after = [n for n in before if n], [n for n in after if n]
    if not before or not after:
        return bool(before) != bool(after)
    left = list(after)
    common = 0
    for name in before:
        hit = next((i for i, other in enumerate(left) if _same_name(name, other)), None)
        if hit is not None:
            common += 1
            left.pop(hit)
    return common * 2 < max(len(before), len(after))


def list_moved(before, after) -> bool:
    (b, b_names), (a, a_names) = before, after
    if not b and not a:
        return _names_differ(b_names, a_names)
    if not b or not a:
        return True
    # Positions: how many buttons are still where a button was.
    pairs = []
    used = set()
    for j, q in enumerate(a):
        hit = next((i for i, p in enumerate(b) if i not in used
                    and abs(p[0] - q[0]) <= MOVED and abs(p[1] - q[1]) <= MOVED), None)
        if hit is not None:
            used.add(hit)
            pairs.append((hit, j))
    if len(pairs) * 5 < 3 * min(len(a), len(b)):
        return True                                   # the buttons shifted: it scrolled
    # Same places: nothing moved, or exactly whole rows. The names on the cards tell.
    if len(b_names) != len(b) or len(a_names) != len(a):
        return _names_differ(b_names, a_names)
    compared = differ = 0
    for i, j in pairs:
        if b_names[i] and a_names[j]:
            compared += 1
            differ += not _same_name(b_names[i], a_names[j])
    return compared > 0 and differ * 2 > compared


@dataclass
class ScrollState:
    scrollable: bool | None = None  # None = not tried yet
    probed_at: float = 0.0
    since: float = 0.0              # when this part of the list came up
    steps: int = 0                  # scroll steps below the top
    most_steps: int = 0             # steps to the bottom, once it was found
    empty_run: int = 0              # parts in a row with nothing to upgrade
    before: tuple = ([], [])        # card marks before the last scroll
    before_sig: object = None       # picture of the cards before the last scroll
    checking: bool = False          # the last scroll down isn't read yet
    going_up: bool = False          # the last scroll to the top isn't read yet
    up_tries: int = 0
    reads: int = 0                  # detector reads when it scrolled
    done_at: float = 0.0            # MacroThread's last "all maxed" time seen
    seen_at: float = 0.0            # last time the manager was handled here
    placed_seen: int = 0            # units placed when last seen
    restart: bool = False           # start the next sweep from the top


class ScrollingUpgrades:
    """Mixin: upgrade every unit in the Unit Overview, not just the 8 on screen."""

    def _new_match(self) -> None:
        super()._new_match()
        self._scroll = ScrollState(since=time.monotonic())

    def _scroll_state(self) -> ScrollState:
        if getattr(self, "_scroll", None) is None:
            self._scroll = ScrollState(since=time.monotonic())
        return self._scroll

    def _note_sweep_start(self, st: ScrollState, now: float) -> None:
        """Things that mean the list must be looked at again from the top."""
        m = self.match
        if st.seen_at and now - st.seen_at > REOPEN_GAP:
            st.restart = True                       # closed and opened again
        st.seen_at = now
        if m.upgrades_done_at != st.done_at:        # a fresh look after "all maxed"
            st.done_at, st.empty_run, st.restart = m.upgrades_done_at, 0, True
        if m.placed != st.placed_seen:              # a new unit: it's in the list somewhere
            st.placed_seen, st.empty_run, st.restart = m.placed, 0, True
            if st.scrollable is False:
                st.scrollable = None                # the new unit may make it scroll

    def _list_moved(self, st: ScrollState, lines: list[OcrLine], title: OcrLine) -> bool:
        """Did the last scroll move the list? The picture first, then the text."""
        _, frame = self.capture.latest_frame()
        change = picture_change(st.before_sig, list_signature(frame, title))
        if change is not None and change >= PICTURE_MOVED:
            return True
        if change is not None and change <= PICTURE_SAME:
            return False
        return list_moved(st.before, card_marks(lines, title))

    def _remember_list(self, st: ScrollState, lines: list[OcrLine], title: OcrLine) -> None:
        st.before = card_marks(lines, title)
        _, frame = self.capture.latest_frame()
        st.before_sig = list_signature(frame, title)

    def _settled(self, st: ScrollState, now: float) -> bool:
        fresh = getattr(self.detector, "latest_count", 0) >= st.reads + 2
        return not (now - st.since < SETTLE or (not fresh and now - st.since < 5))

    def _on_unit_manager(self, hwnd: int) -> None:
        m, cfg = self.match, self.settings
        st = self._scroll_state()
        now = time.monotonic()
        self._note_sweep_start(st, now)
        upgrading = cfg.upgrade_units and not m.upgrades_done and not (
            cfg.place_units and m.pending and not self._place_paused())
        det = self.detector.latest
        title = overview_title(det.lines) if det is not None and det.screen == "unit_manager" else None
        if not upgrading or title is None:
            if st.checking or st.going_up:
                st.restart = True                   # a scroll was left unread: position unknown
            st.checking = st.going_up = False
            super()._on_unit_manager(hwnd)
            return
        if st.restart:
            st.restart, st.empty_run = False, 0
            if st.steps > 0 or st.checking or st.going_up:
                self._scroll_to_top(hwnd, title, det.lines, verify=False)
                return
            st.checking = False
            st.since = now
        if st.going_up:
            if not self._settled(st, now):
                return
            st.going_up = False
            if st.up_tries < UP_RETRIES and not self._list_moved(st, det.lines, title):
                st.up_tries += 1
                self.log.emit("The unit list didn't go back to the top — scrolling up again.", "Info")
                self._scroll_to_top(hwnd, title, det.lines)
                return
            st.up_tries = 0
            st.since = now
        if st.checking:
            if not self._settled(st, now):
                return                              # still scrolling / not read since
            st.checking = False
            limit = st.most_steps + 2 if st.most_steps else MAX_STEPS
            if not self._list_moved(st, det.lines, title) or st.steps >= limit:
                if st.steps == 0:
                    st.scrollable, st.probed_at = False, now     # nothing below: leave it
                else:
                    st.most_steps = max(st.most_steps, st.steps)  # the bottom: remember how deep
                    self._scroll_to_top(hwnd, title, det.lines)
                    return
            else:
                if st.scrollable is not True:
                    self.log.emit("The unit list scrolls — upgrading every part of it "
                                  "(top to bottom, then back to the top).", "Info")
                st.scrollable = True
                st.steps += 1
        if st.scrollable is False:
            if now - st.probed_at < REPROBE:
                super()._on_unit_manager(hwnd)      # one screenful: nothing changes
                return
            st.scrollable = None                    # more units may have gone down
        _, frame = self.capture.latest_frame()
        buttons = (find_green_buttons(frame) if frame is not None else []) + [
            l for l in det.lines if _norm(l.text).startswith("upg")]
        has_work = bool(self._buttons_to_upgrade(det.lines, buttons))
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

    def _buttons_to_upgrade(self, lines: list[OcrLine], buttons: list[OcrLine]) -> list[OcrLine]:
        """The buttons that count as work (PlaceOnlyUnits leaves some out)."""
        return buttons

    def _list_spot(self, title: OcrLine) -> tuple[float, float]:
        return title.center_x, title.y + title.h / 2 + LIST_DY * title.w

    def _scroll_down(self, hwnd: int, title: OcrLine, lines: list[OcrLine]) -> None:
        st = self._scroll
        self._remember_list(st, lines, title)
        st.checking, st.since = True, time.monotonic()
        st.reads = getattr(self.detector, "latest_count", 0)
        self.match.no_upgrade_reads = 0
        part = st.steps + 2
        total = f" of {st.most_steps + 1}" if st.most_steps and part <= st.most_steps + 1 else ""
        self._say(f"Upgrading — unit list part {part}{total} (scrolling down)", log=False)
        inp.scroll(hwnd, *self._list_spot(title), SCROLL_NOTCHES)
        self._park_mouse(hwnd)

    def _scroll_to_top(self, hwnd: int, title: OcrLine, lines: list[OcrLine] | None = None,
                       verify: bool = True) -> None:
        """Back to the top; with verify, the next read checks that it moved."""
        st = self._scroll
        deep = max(st.steps, st.most_steps) + 2
        notches = max(TOP_NOTCHES, deep * SCROLL_NOTCHES * 2)
        self._remember_list(st, lines or [], title)
        st.going_up = verify and (st.steps > 0 or st.up_tries > 0)
        st.checking = False
        st.steps, st.since = 0, time.monotonic()
        st.reads = getattr(self.detector, "latest_count", 0)
        self.match.no_upgrade_reads = 0
        self._say("Upgrading — back to the top of the unit list (part 1)", log=False)
        inp.scroll(hwnd, *self._list_spot(title), -notches)
        self._park_mouse(hwnd)
