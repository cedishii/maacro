"""Where to try placing units, and which unit manager rows to upgrade first.

Units on keys 1, 5 and 6 work from anywhere, so instead of saved spots per
map, MAACRO tries spots in rings around the middle of the screen (where the
player stands) and keeps the first one the game accepts.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .vision.ocr import OcrLine
from .vision.screens import _norm, fuzzy_in

# Parts of the window covered by the game's UI (fractions of width/height).
UI_LEFT, UI_RIGHT = 0.13, 0.84      # side menus / level info panel
# Bottom stays well above the hotbar: the Place/Rotate/Cancel menu opens next to
# the mouse and would cover the placed/total counter.
UI_TOP, UI_BOTTOM = 0.16, 0.68      # wave bar / hotbar


def candidate_spots(width: int, height: int, used: list[tuple[float, float]] | None = None,
                    radii=(0.12, 0.19, 0.26), steps: int = 12) -> list[tuple[float, float]]:
    """Spots to try, nearest the middle first, skipping UI and spots already used."""
    used = used or []
    cx, cy = width / 2, height / 2
    spots = []
    for ring, radius in enumerate(radii):
        r = radius * height
        for i in range(steps):
            # Offset each ring so spots don't line up.
            angle = 2 * math.pi * (i + 0.5 * ring) / steps
            x, y = cx + r * math.cos(angle), cy + r * math.sin(angle) * 0.8
            if not (UI_LEFT * width < x < UI_RIGHT * width and UI_TOP * height < y < UI_BOTTOM * height):
                continue
            if any(math.hypot(x - ux, y - uy) < 0.05 * height for ux, uy in used):
                continue
            spots.append((x, y))
    return spots


def placeable_spots(frame: np.ndarray, limit: int = 30) -> list[tuple[float, float]]:
    """Spots where a unit can go, from a frame taken *in placement mode*.

    In placement mode the game paints every surface you can't place on red,
    so anything that isn't red (cobblestone, grass) is a candidate. Spots
    near the yellow-arrow path come first, as the player suggested, then
    those nearest the middle.
    """
    height, width = frame.shape[:2]
    scale = 4
    small = cv2.resize(np.ascontiguousarray(frame[:, :, :3]), (width // scale, height // scale),
                       interpolation=cv2.INTER_AREA)
    b, g, r = (small[..., i].astype(np.int16) for i in range(3))
    red = (r > g + 50) & (r > b + 50)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (20, 150, 170), (35, 255, 255)) > 0
    # Ground = not red, not the yellow path itself, not too dark (shadows/void).
    ground = (~red & ~yellow & (hsv[..., 2] > 60)).astype(np.uint8)
    # Units need some room: keep only spots with ground all around them.
    room = max(3, int(0.03 * height / scale) | 1)
    ground = cv2.erode(ground, np.ones((room, room), np.uint8))

    # Distance to the yellow path (in small pixels); far away if there's none.
    if yellow.any():
        to_path = cv2.distanceTransform((~yellow).astype(np.uint8), cv2.DIST_L2, 3)
    else:
        to_path = np.full(ground.shape, 1e6, np.float32)

    step = max(2, int(0.03 * height / scale))
    cx, cy = width / 2, height / 2
    spots = []
    for y in range(0, ground.shape[0], step):
        for x in range(0, ground.shape[1], step):
            if not ground[y, x]:
                continue
            fx, fy = x * scale, y * scale
            if not (UI_LEFT * width < fx < UI_RIGHT * width and UI_TOP * height < fy < UI_BOTTOM * height):
                continue
            # Not on top of the player (they spawn in the middle).
            if math.hypot(fx - cx, fy - cy) < 0.06 * height:
                continue
            near_path = min(float(to_path[y, x]) * scale, 0.5 * height)
            spots.append((near_path + 0.3 * math.hypot(fx - cx, fy - cy), (float(fx), float(fy))))
    spots.sort()
    # Spread the picks out, so a handful of tries covers different ground.
    picked: list[tuple[float, float]] = []
    for _, (x, y) in spots:
        if all(math.hypot(x - px, y - py) >= 0.05 * height for px, py in picked):
            picked.append((x, y))
            if len(picked) >= limit:
                break
    return picked


def red_mask(frame: np.ndarray) -> np.ndarray:
    """Where the game paints 'can't place here' red (roofs, the road, and the
    discs under units that are already placed). Same rule as placeable_spots."""
    b, g, r = (frame[..., i].astype(np.int16) for i in range(3))
    return (r > g + 50) & (r > b + 50)


def drop_red_spots(frame: np.ndarray, spots: list[tuple[float, float]],
                   radius_fraction: float = 0.02, max_red: float = 0.4) -> list[tuple[float, float]]:
    """Keep only the spots that aren't mostly red in a frame taken *in placement
    mode*, so taken or blocked spots are skipped without spending a click."""
    if not spots:
        return []
    height, width = frame.shape[:2]
    red = red_mask(frame[:, :, :3])
    r = max(3, int(radius_fraction * height))
    kept = []
    for x, y in spots:
        x0, x1 = max(0, int(x) - r), min(width, int(x) + r + 1)
        y0, y1 = max(0, int(y) - r), min(height, int(y) + r + 1)
        window = red[y0:y1, x0:x1]
        if window.size and window.mean() <= max_red:
            kept.append((x, y))
    return kept


def path_spots(frame: np.ndarray, limit: int = 40) -> list[tuple[float, float]]:
    """Spots on the ground just beside the enemy path (bright red), nearest the
    middle first. Units are easiest to place there.

    Use a frame taken *before* pressing a unit key: the red 'can't place here'
    circle would otherwise look like path.
    """
    height, width = frame.shape[:2]
    scale = 4
    small = cv2.resize(np.ascontiguousarray(frame[:, :, :3]), (width // scale, height // scale),
                       interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 150, 150), (8, 255, 255)) | cv2.inRange(hsv, (172, 150, 150), (180, 255, 255))
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))   # drop specks

    def disc(fraction: float) -> np.ndarray:
        size = max(3, int(fraction * height / scale) | 1)
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    inner = cv2.dilate(red, disc(0.05))
    outer = cv2.dilate(red, disc(0.12))
    ring = (outer > 0) & (inner == 0)

    step = max(2, int(0.045 * height / scale))
    cx, cy = width / 2, height / 2
    spots = []
    for y in range(0, ring.shape[0], step):
        for x in range(0, ring.shape[1], step):
            if not ring[y, x]:
                continue
            fx, fy = x * scale, y * scale
            if UI_LEFT * width < fx < UI_RIGHT * width and UI_TOP * height < fy < UI_BOTTOM * height:
                spots.append((float(fx), float(fy)))
    spots.sort(key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
    return spots[:limit]


def spots_to_try(width: int, height: int, placed: list[tuple[float, float]]
                 ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(spots next to units already placed, general spots around the middle).

    Ground beside a valid spot is usually valid too, so those go first."""
    near = []
    for px, py in placed:
        for i in range(8):
            angle = 2 * math.pi * i / 8
            x = px + 0.07 * height * math.cos(angle)
            y = py + 0.07 * height * math.sin(angle) * 0.8
            if UI_LEFT * width < x < UI_RIGHT * width and UI_TOP * height < y < UI_BOTTOM * height \
                    and all(math.hypot(x - ux, y - uy) >= 0.05 * height for ux, uy in placed):
                near.append((x, y))
    return near, candidate_spots(width, height, used=placed)


def find_green_buttons(frame: np.ndarray) -> list[OcrLine]:
    """The unit manager's green 'Upg' buttons, found by colour.

    Text recognition misses them often; their solid bright green doesn't.
    'Max' buttons are grey and 'First' buttons blue, so they're never matched.
    Only the right part of the window is searched (where the manager opens),
    so grass and health bars elsewhere don't count.
    """
    height, width = frame.shape[:2]
    left = int(width * 0.55)
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[:, left:, :3]), cv2.COLOR_BGR2HSV)
    # (Some units show a gold Upg button for their last upgrade; its gradient
    # can't be told apart from yellow text by colour, so the macro finds those
    # by their "Upg" text instead.)
    mask = cv2.inRange(hsv, (45, 200, 170), (65, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    buttons = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (0.035 * width < w < 0.12 * width and 0.025 * height < h < 0.08 * height):
            continue
        if w < 1.8 * h or cv2.contourArea(contour) < 0.5 * w * h:
            continue
        buttons.append(OcrLine("Upg", left + x, y, w, h))
    return sorted(buttons, key=lambda b: (b.y, b.x))


def upgrade_order(lines: list[OcrLine], unit_names: dict[str, str],
                  priority: list[str], buttons: list[OcrLine] | None = None) -> list[OcrLine]:
    """The unit manager's 'Upg' buttons, highest-priority unit first.

    `buttons` are found by colour if given, otherwise by their text. Each Upg
    button belongs to the unit whose name sits nearest it, on its left.
    """
    if buttons is None:
        buttons = [l for l in lines if _norm(l.text).startswith("upg")]
    names = {key: name for key, name in unit_names.items() if name.strip()}

    def rank(button: OcrLine) -> int:
        best_key, best_dist = None, float("inf")
        for line in lines:
            if line is button or line.x > button.x + 10:
                continue
            for key, name in names.items():
                if fuzzy_in(name, line.text, 0.65):
                    dist = abs(line.y - button.y) + 0.5 * abs(line.x - button.x)
                    if dist < best_dist:
                        best_key, best_dist = key, dist
        if best_key in priority:
            return priority.index(best_key)
        return len(priority)

    return sorted(buttons, key=rank)
