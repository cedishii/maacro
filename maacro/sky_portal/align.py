"""Lining the live view up with the Sky Portal picture.

The camera follows the character, and the character doesn't always spawn on
the same spot (a step forward, back or to the side). Everything on screen is
then shifted by the same amount, so every unit spot is shifted too.

A few patches of scenery from the reference picture (buildings, path, fence:
away from the drawn circles, the players and the game's panels) are looked
for in the live frame near where they should be. The shift most of them
agree on is the spawn offset.
"""
from __future__ import annotations

import cv2
import numpy as np

# Scenery patches in sky_portal_reference.png (screenshot pixels, title bar
# included), clear of the drawn circle, the unit spots and the players:
# left, top, right, bottom.
PATCHES = [
    (900, 130, 1170, 290),   # the purple building right of the path
    (370, 265, 640, 360),    # the left building's wall, under the balcony
    (100, 455, 400, 535),    # planks and fence, lower left
    (880, 300, 1120, 420),   # snow and lamp post right of the path
]
SEARCH = 0.08       # × width: how far a patch is looked for around its place
MIN_SCORE = 0.55    # match quality for a patch to count
AGREE = 0.012       # × width: patches within this of each other agree


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(np.ascontiguousarray(image[:, :, :3]), cv2.COLOR_BGR2GRAY)
    return image


def spawn_shift(reference: np.ndarray, titlebar: int, frame: np.ndarray) -> tuple[float, float, int] | None:
    """(dx, dy, patches agreeing) in live pixels, or None if it can't tell."""
    ref = _gray(reference)[titlebar:]
    live = _gray(frame)
    h, w = live.shape
    scale = w / ref.shape[1]
    if abs(scale - 1) > 0.01:
        ref = cv2.resize(ref, (w, int(round(ref.shape[0] * scale))))
    search = int(SEARCH * w)
    found = []
    for left, top, right, bottom in PATCHES:
        x0, y0 = int(left * scale), int((top - titlebar) * scale)
        x1, y1 = int(right * scale), int((bottom - titlebar) * scale)
        patch = ref[y0:y1, x0:x1]
        sx0, sy0 = max(0, x0 - search), max(0, y0 - search)
        sx1, sy1 = min(w, x1 + search), min(h, y1 + search)
        area = live[sy0:sy1, sx0:sx1]
        if patch.size == 0 or area.shape[0] < patch.shape[0] or area.shape[1] < patch.shape[1]:
            continue
        result = cv2.matchTemplate(area, patch, cv2.TM_CCOEFF_NORMED)
        _, score, _, (mx, my) = cv2.minMaxLoc(result)
        if score >= MIN_SCORE:
            found.append((sx0 + mx - x0, sy0 + my - y0))
    if not found:
        return None
    # The largest group of patches that agree.
    tol = AGREE * w
    best = max(([q for q in found if abs(q[0] - p[0]) <= tol and abs(q[1] - p[1]) <= tol] for p in found),
               key=len)
    if len(best) < 2 and len(found) > 1:
        return None
    dx = float(np.median([p[0] for p in best]))
    dy = float(np.median([p[1] for p in best]))
    return dx, dy, len(best)
