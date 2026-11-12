"""The placed/total counter shown above the selected hotbar unit ("0/3", "2/2").

This is MAACRO's proof that a unit was placed: the first number goes up.

The hotbar always has 6 evenly spaced cards centred at the bottom, so the
counter above card N is found by position. Its characters (white, or red when
the unit is full, with a black outline) are read by shape: Windows text
recognition misses them too often, especially over red roofs.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from .numbers import DigitShapeReader
from .ocr import OcrReader

COUNT_RE = re.compile(r"(?<![\d/])(\d)\s*/\s*(\d)(?![\d/.])")
# Hotbar geometry, as fractions of the window size.
CARD_SPACING = 0.0565           # × width, centre to centre
COUNTER_TOP, COUNTER_BOTTOM = 0.815, 0.88   # × height
COUNTER_HALF_WIDTH = 0.032      # × width
# Fallback search strip when the slot isn't known.
BAND_TOP, BAND_BOTTOM = 0.74, 0.92
BAND_HALF_WIDTH = 0.33


SAMPLES_DIR = Path(__file__).resolve().parents[1] / "assets" / "digits"


class CounterShapeReader(DigitShapeReader):
    """DigitShapeReader that also knows '/', plus real samples from the game
    (e.g. its open-top 4) saved in maacro/assets/digits as '<char>_<name>.png'."""
    CHARS = "0123456789/"
    MIN_FILL = 0.28     # card-frame corners are thin arcs; characters are solid

    def _build_templates(self):
        from PIL import Image, ImageDraw, ImageFont
        templates = []
        for sample in sorted(SAMPLES_DIR.glob("*.png")):
            char = "/" if sample.stem.startswith("slash") else sample.stem[0]
            mask = cv2.imread(str(sample), cv2.IMREAD_GRAYSCALE)
            shape = self._normalize(mask) if mask is not None else None
            if shape is not None:
                templates.append((char, shape))
        for font_name in self.FONTS:
            path = Path("C:/Windows/Fonts") / f"{font_name}.ttf"
            if not path.exists():
                continue
            font = ImageFont.truetype(str(path), 80)
            for char in self.CHARS:
                image = Image.new("L", (120, 120), 0)
                ImageDraw.Draw(image).text((20, 5), char, fill=255, font=font)
                shape = self._normalize((np.array(image) > 128).astype(np.uint8) * 255)
                if shape is not None:
                    templates.append((char, shape))
        return templates

    def read_counter(self, crop: np.ndarray) -> tuple[int, int] | None:
        b, g, r = (crop[..., i].astype(np.int16) for i in range(3))
        white = (b > 185) & (g > 185) & (r > 185)
        red = (r > 190) & (g < 120) & (b < 120)
        height, width = crop.shape[:2]
        for mask in (white, red):
            mask = mask.astype(np.uint8) * 255
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            chars = []      # (left, right, char, score, top, height)
            for i in range(1, count):
                x, y, w, h, area = stats[i]
                # Characters: a decent height, solid, not touching the crop's
                # sides or bottom (the card frame and the "Lv." text do).
                if not (0.25 * height <= h <= 0.75 * height) or area < 12:
                    continue
                if x <= 0 or x + w >= width or y + h >= height or area < self.MIN_FILL * w * h:
                    continue
                result = self._classify((labels == i).astype(np.uint8) * 255)
                if result is not None and result[1] >= 0.6:
                    chars.append((x, x + w, result[0], result[1], y, h))
            # Read the digits right before and right after the '/', on the same
            # line and the same height (background sparkles aren't).
            slashes = sorted((c for c in chars if c[2] == "/"), key=lambda c: -c[3])
            for slash in slashes:
                s_left, s_right, _, _, s_top, s_h = slash
                gap = max(4, s_right - s_left)

                def aligned(c):
                    return (c[2].isdigit() and abs(c[4] - s_top) <= 0.3 * s_h
                            and 0.7 * s_h <= c[5] <= 1.3 * s_h)

                lefts = [c for c in chars if aligned(c) and 0 <= s_left - c[1] <= gap]
                rights = [c for c in chars if aligned(c) and 0 <= c[0] - s_right <= gap]
                if lefts and rights:
                    left = max(lefts, key=lambda c: c[1])
                    right = min(rights, key=lambda c: c[0])
                    placed, total = int(left[2]), int(right[2])
                    if 0 < total <= 9 and placed <= total:
                        return placed, total
        return None


_shapes: CounterShapeReader | None = None


def _shape_reader() -> CounterShapeReader | None:
    global _shapes
    if _shapes is None:
        try:
            _shapes = CounterShapeReader()
        except Exception:
            return None
    return _shapes


def counter_box(width: int, height: int, slot: int) -> tuple[int, int, int, int]:
    """Where the counter above hotbar card `slot` (1–6) is: left, top, right, bottom."""
    cx = width / 2 + (slot - 3.5) * CARD_SPACING * width
    return (int(cx - COUNTER_HALF_WIDTH * width), int(COUNTER_TOP * height),
            int(cx + COUNTER_HALF_WIDTH * width), int(COUNTER_BOTTOM * height))


def _ocr_count(image: np.ndarray, ocr: OcrReader, scale: float) -> tuple[int, int] | None:
    big = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    for line in ocr.read(big):
        match = COUNT_RE.search(line.text)
        if match:
            placed, total = int(match.group(1)), int(match.group(2))
            if 0 < total <= 9 and placed <= total:
                return placed, total
    return None


def read_unit_count(frame: np.ndarray, ocr: OcrReader, slot: int | None = None) -> tuple[int, int] | None:
    """(placed, total) for the selected unit, or None if no counter is readable.

    With `slot` (the hotbar key pressed), only the spot above that card is read.
    """
    height, width = frame.shape[:2]
    if slot is not None:
        left, top, right, bottom = counter_box(width, height, slot)
        crop = np.ascontiguousarray(frame[top:bottom, max(0, left):min(width, right), :3])
        if crop.size == 0:
            return None
        shapes = _shape_reader()
        if shapes is not None:
            count = shapes.read_counter(crop)
            if count is not None:
                return count
        padded = cv2.copyMakeBorder(crop, 10, 10, 10, 10, cv2.BORDER_REPLICATE)
        return _ocr_count(padded, ocr, 4)

    top, bottom = int(height * BAND_TOP), int(height * BAND_BOTTOM)
    left = int(max(0, width / 2 - BAND_HALF_WIDTH * width))
    right = int(min(width, width / 2 + BAND_HALF_WIDTH * width))
    band = np.ascontiguousarray(frame[top:bottom, left:right, :3])
    red_only = cv2.cvtColor(255 - band[:, :, 2], cv2.COLOR_GRAY2BGR)
    for image in (band, red_only):
        count = _ocr_count(image, ocr, 2)
        if count is not None:
            return count
    return None
