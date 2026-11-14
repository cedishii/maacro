"""Reading a unit's upgrade level in the Unit Overview.

Under each unit card is a bar with one segment per upgrade (4 for Elyssia
and the C.E.O., 8 for Fishi and Phoenix…). Done upgrades are bright (green
or gold), the rest dark green or dark olive. The level is the number of
bright segments.

The bar is found below the card's Upg button: the first band of mostly-green
rows between UPPER and LOWER × the button's height under its top, across the
card (from 1.2 button widths left of the button to its right edge).
"""
from __future__ import annotations

import cv2
import numpy as np

UPPER, LOWER = 1.2, 5.0     # × button height below the button's top: where the bar is looked for
LEFT = 1.2                  # × button width left of the button: the card's left edge
# Segments are green or gold; done ones bright, the rest dark (white outlines
# only preview the next upgrade).
GREEN = ((15, 90, 40), (85, 255, 255))      # any segment
BRIGHT = ((15, 120, 175), (85, 255, 255))   # a done segment
MIN_SEGMENT = 4             # px: narrower runs are noise


def _runs(columns: np.ndarray) -> int:
    count, run = 0, 0
    for on in list(columns) + [False]:
        if on:
            run += 1
        else:
            if run >= MIN_SEGMENT:
                count += 1
            run = 0
    return count


BLUE = ((95, 120, 120), (130, 255, 255))    # the card's "First" button


def upgrade_level(frame: np.ndarray, button) -> tuple[int, int] | None:
    """(done, segments) for the card whose Upg button is `button`, or None.

    `button` can be the green/gold button or just its "Upg" text: the bar is
    looked for below the blue First button under it."""
    height, width = frame.shape[:2]
    x0 = int(max(0, button.x - LEFT * button.w))
    x1 = int(min(width, button.x + button.w))
    y0 = int(max(0, button.y))
    y1 = int(min(height, button.y + LOWER * max(button.h, 0.05 * height)))
    if x1 - x0 < 20 or y1 - y0 < 10:
        return None
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1, :3]), cv2.COLOR_BGR2HSV)
    # The First button: rows mostly blue under the Upg button.
    bx0, bx1 = int(button.x) - x0, int(button.x + button.w) - x0
    blue = (cv2.inRange(hsv[:, bx0:bx1], *BLUE) > 0).sum(axis=1) >= 0.5 * (bx1 - bx0)
    blue_rows = np.flatnonzero(blue)
    if not blue_rows.size:
        return None
    start = blue_rows[0]
    while start + 1 < len(blue) and blue[start + 1]:
        start += 1
    green = cv2.inRange(hsv, *GREEN) > 0
    strong = [y for y in np.flatnonzero(green.sum(axis=1) >= 0.6 * (x1 - x0)) if y > start]
    if not strong:
        return None
    top = strong[0]
    band = [top]
    while band[-1] + 1 in strong:
        band.append(band[-1] + 1)
    if len(band) < 3:
        return None
    rows = slice(top, top + max(2, len(band) // 2))     # the top half: brightest when done
    bright = cv2.inRange(hsv[rows], *BRIGHT) > 0
    segments = _runs(green[band[0]:band[-1] + 1].any(axis=0))
    done = _runs(bright.any(axis=0))
    if not segments:
        return None
    return min(done, segments), segments
