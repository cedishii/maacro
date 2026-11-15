"""Units that can only go on green spots (Phoenix).

Some units show where they can go when you pick them up: the game paints
those spots bright green. For these units ("green_units" in the mode's
settings) the placement spots come from the green areas of the frame taken
in placement mode, and nothing else is tried (no automatic spots: anywhere
else would fail anyway). If there's no green spot free right now, the unit
waits its turn (MacroThread's "try the others first, back to it later"), so
it's tried again from time to time.

GreenSpots is a mixin for MacroThread subclasses. macro.py's source isn't
changed; its two automatic-spot helpers are wrapped here and return nothing
only while a green unit is being placed.
"""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from . import macro as _macro

GREEN = ((50, 200, 180), (70, 255, 255))    # the painted spots: pure bright green
STEP = 0.035        # × height between candidate spots
EDGE = 0.3          # × STEP: a spot must be this far inside the green
MIN_AREA = 0.002    # × frame area: smaller green bits (health bars, text) don't count
LIMIT = 40

_local = threading.local()


def _wrap(function, nothing):
    def wrapper(*args, **kwargs):
        if getattr(_local, "green_only", False):
            return nothing()
        return function(*args, **kwargs)
    wrapper._green_spots = True
    return wrapper


if not getattr(_macro.placeable_spots, "_green_spots", False):
    _macro.placeable_spots = _wrap(_macro.placeable_spots, list)
    _macro.spots_to_try = _wrap(_macro.spots_to_try, lambda: ([], []))


def green_spots(frame: np.ndarray, limit: int = LIMIT) -> list[tuple[float, float]]:
    """Points well inside the bright green areas, biggest areas first."""
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[:, :, :3]), cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *GREEN)
    # Keep clear of the top bar (title, health bars), the hotbar and the side panel.
    mask[: int(0.15 * height)] = 0
    mask[int(0.85 * height):] = 0
    mask[:, int(0.88 * width):] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    step = max(8, int(STEP * height))
    inside = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    areas = sorted((i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_AREA * width * height
                    and stats[i, cv2.CC_STAT_HEIGHT] >= step), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    spots = []
    for i in areas:
        x0, y0, w, h = (stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
                        stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        for y in range(y0 + step // 2, y0 + h, step):
            for x in range(x0 + step // 2, x0 + w, step):
                if labels[y, x] == i and inside[y, x] >= EDGE * step:
                    spots.append((float(x), float(y)))
    return spots[:limit]


class GreenZones:
    """Stands in for a map's zones while a green unit is placed: its spots
    are the green areas of the latest frame (taken in placement mode)."""

    def __init__(self, thread):
        self.thread, self.name = thread, "green spot"
        self.walk, self.looked, self.found = None, False, 0

    def spots(self, lines, frame_w: int, frame_h: int, step_fraction: float = STEP):
        self.looked = True
        _, frame = self.thread.capture.latest_frame()
        found = green_spots(frame) if frame is not None else []
        self.found = len(found)
        return found


class GreenSpots:
    """Mixin: units in `green_units` are only placed on the green spots."""

    def _place_next(self, hwnd: int) -> None:
        m = self.match
        key = m.pending[0] if m.pending else None
        if key is None or key not in (getattr(self.settings, "green_units", []) or []):
            super()._place_next(hwnd)
            return
        green, saved = GreenZones(self), self._map
        self._map = green
        self._last_done["zone_fit_log"] = time.monotonic()   # not "couldn't line up the zones"
        _local.green_only = True
        try:
            super()._place_next(hwnd)
        finally:
            _local.green_only = False
            self._map = saved
        if green.looked and not green.found and key in m.pending:
            if self._cooldown(f"no_green_{key}", 30):
                self.log.emit(f"{self._unit_label(key)}: no green spot on screen right now — "
                              "placing the others, trying again later.", "Info")
            self._unit_stuck(hwnd, key, room=False)
