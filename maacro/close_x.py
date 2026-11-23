"""Finding a window's red X (close) button by colour.

Anime Adventures' windows (Areas, Misty Village Stages, Join Matchmaking,
Captcha, shops…) all close with the same button: a red rounded square with a
white X, at the window's top-right corner. It's found as a red blob, about
square, with white inside; the red Cancel buttons are wide, so they're not it.
"""
from __future__ import annotations

import cv2
import numpy as np

from .vision.ocr import OcrLine


def red_x_buttons(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) of every red X button on the picture."""
    if frame is None:
        return []
    height = frame.shape[0]
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[..., :3]), cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 140, 130), (8, 255, 255)) | cv2.inRange(hsv, (170, 140, 130), (180, 255, 255))
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    white = cv2.inRange(hsv, (0, 0, 200), (180, 60, 255))
    count, _, stats, _ = cv2.connectedComponentsWithStats(red)
    found = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        # Windows' X: 59-89 px tall on a 991 px picture. The unit cards' own
        # red X (they SELL the unit) are ~43 px: never matched.
        if not (0.052 * height <= h <= 0.13 * height and 0.6 <= w / h <= 1.9):
            continue
        if area < 0.35 * w * h:
            continue
        inner = white[y + h // 5:y + h - h // 5, x + w // 5:x + w - w // 5]
        if inner.size == 0 or np.count_nonzero(inner) < 0.08 * inner.size:
            continue                                  # no white X inside
        found.append((x, y, w, h))
    return found


def close_button(frame: np.ndarray, title: OcrLine | None = None) -> tuple[float, float] | None:
    """Centre of the X that closes the window with this title (the nearest X
    up and to the right of it), or of the top-most X when no title is given."""
    buttons = red_x_buttons(frame)
    if not buttons:
        return None
    if title is not None:
        right_of = [b for b in buttons if b[0] + b[2] / 2 > title.x + title.w / 2
                    and b[1] < title.y + 3 * max(title.h, 10)]
        if not right_of:
            return None
        x, y, w, h = min(right_of, key=lambda b: abs(b[1] - title.y) + 0.5 * abs(b[0] - (title.x + title.w)))
    else:
        x, y, w, h = min(buttons, key=lambda b: (b[1], -b[0]))
    return x + w / 2, y + h / 2
