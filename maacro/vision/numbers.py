"""Reading gameplay numbers (card votes, yen, ...) from part of a frame.

The macro only talks to the `NumberReader` interface. Readers ("providers")
are registered in PROVIDERS, so another one can be added later without
changing the macro. Today there is one: the built-in reader, which uses the
same Windows text recognition as the rest of MAACRO.

Every reader is wrapped in `GuardedNumberReader`, which:
- turns any error into `None` plus a logged warning, and
- refuses to read anything while the matchmaking verification (captcha)
  screen is showing. That screen is always left to the player.
"""
from __future__ import annotations

import re
from typing import Callable, Protocol

import cv2
import numpy as np

from .ocr import OcrReader

Box = tuple[int, int, int, int]          # left, top, right, bottom (frame pixels)
LogFn = Callable[[str, str], None]       # message, level
PROTECTED_SCREENS = frozenset({"captcha"})

_DIGITS = re.compile(r"\d+")
# OCR often mistakes these for digits in the game's font.
_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "S": "5", "s": "5",
                             "I": "1", "l": "1", "|": "1", "i": "1", "B": "8", "Z": "2"})


class NumberReader(Protocol):
    name: str

    def read(self, frame: np.ndarray, box: Box) -> str | None:
        """The number inside `box`, as a string (keeps leading zeros), or None."""
        ...


def extract_number(text: str, lookalikes: bool = False) -> str | None:
    """The longest run of digits in `text`, or None."""
    if lookalikes:
        text = text.translate(_LOOKALIKES)
    runs = _DIGITS.findall(text)
    return max(runs, key=len) if runs else None


def crop(frame: np.ndarray, box: Box) -> np.ndarray | None:
    left, top, right, bottom = box
    h, w = frame.shape[:2]
    left, right = max(0, int(left)), min(w, int(right))
    top, bottom = max(0, int(top)), min(h, int(bottom))
    if right - left < 2 or bottom - top < 2:
        return None
    return frame[top:bottom, left:right]


class DigitShapeReader:
    """Reads short white numbers (like card vote counts) by comparing each digit's
    shape with digits 0–9 drawn in several bold Windows fonts.

    Windows text recognition is poor at lone characters ("3", "1"); this isn't.
    """
    SIZE = (32, 48)            # width, height every digit is scaled to
    FONTS = ("segoeuib", "arialbd", "verdanab", "tahomabd", "calibrib", "seguibl", "ariblk")
    MIN_SCORE = 0.7

    def __init__(self) -> None:
        self._templates = self._build_templates()
        if not self._templates:
            raise RuntimeError("no Windows fonts found to build digit shapes")

    def _normalize(self, mask: np.ndarray) -> np.ndarray | None:
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return None
        blob = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        width, height = self.SIZE
        new_w = max(1, min(width, int(round(blob.shape[1] * height / blob.shape[0]))))
        scaled = cv2.resize(blob, (new_w, height), interpolation=cv2.INTER_AREA)
        out = np.zeros((height, width), np.float32)
        x0 = (width - new_w) // 2
        out[:, x0:x0 + new_w] = scaled / 255.0
        return out

    def _build_templates(self) -> list[tuple[str, np.ndarray]]:
        from pathlib import Path
        from PIL import Image, ImageDraw, ImageFont
        templates = []
        for font_name in self.FONTS:
            path = Path("C:/Windows/Fonts") / f"{font_name}.ttf"
            if not path.exists():
                continue
            font = ImageFont.truetype(str(path), 80)
            for digit in "0123456789":
                image = Image.new("L", (120, 120), 0)
                ImageDraw.Draw(image).text((20, 5), digit, fill=255, font=font)
                shape = self._normalize((np.array(image) > 128).astype(np.uint8) * 255)
                if shape is not None:
                    templates.append((digit, shape))
        return templates

    def _classify(self, mask: np.ndarray) -> tuple[str, float] | None:
        shape = self._normalize(mask)
        if shape is None:
            return None
        best_digit, best_score = None, -1.0
        for digit, template in self._templates:
            denom = np.sqrt((shape * shape).sum() * (template * template).sum())
            score = float((shape * template).sum() / denom) if denom else 0.0
            if score > best_score:
                best_digit, best_score = digit, score
        return (best_digit, best_score) if best_digit else None

    def read_image(self, part: np.ndarray) -> str | None:
        gray = cv2.cvtColor(part[..., :3], cv2.COLOR_BGR2GRAY)
        mask = (gray > 200).astype(np.uint8) * 255
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        height = mask.shape[0]
        blobs = [i for i in range(1, count)
                 if stats[i, cv2.CC_STAT_HEIGHT] >= height * 0.2 and stats[i, cv2.CC_STAT_AREA] >= 15]
        if not blobs:
            return None
        # Digits are about as tall as the tallest blob and sit near the middle row.
        tallest = max(stats[i, cv2.CC_STAT_HEIGHT] for i in blobs)
        blobs = [i for i in blobs if stats[i, cv2.CC_STAT_HEIGHT] >= tallest * 0.7
                 and abs(centers[i][1] - height / 2) < height * 0.3]
        digits = []
        for i in sorted(blobs, key=lambda i: stats[i, cv2.CC_STAT_LEFT]):
            result = self._classify((labels == i).astype(np.uint8) * 255)
            if result is None or result[1] < self.MIN_SCORE:
                return None
            digits.append(result[0])
        return "".join(digits) or None


class BuiltinNumberReader:
    """Crops the box and reads it with Windows text recognition; for short
    numbers it can't read, falls back to digit shape matching."""
    name = "built-in"

    def __init__(self, ocr: OcrReader | None = None, scale: float = 3.0) -> None:
        self._ocr = ocr or OcrReader()
        self._scale = scale
        try:
            self._shapes: DigitShapeReader | None = DigitShapeReader()
        except Exception:
            self._shapes = None

    def read(self, frame: np.ndarray, box: Box) -> str | None:
        part = crop(frame, box)
        if part is None:
            return None
        part = part[..., :3]
        big = cv2.resize(part, None, fx=self._scale, fy=self._scale,
                         interpolation=cv2.INTER_CUBIC)
        pad = int(10 * self._scale)
        big = cv2.copyMakeBorder(big, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        text = " ".join(line.text for line in self._ocr.read(big))
        number = extract_number(text)
        if number is None and self._shapes is not None:
            number = self._shapes.read_image(part)
        return number


class GuardedNumberReader:
    """Wraps a provider with error handling, logging and the captcha boundary."""

    def __init__(self, inner: NumberReader, current_screen: Callable[[], str],
                 log: LogFn | None = None) -> None:
        self.inner = inner
        self.name = inner.name
        self._current_screen = current_screen
        self._log = log or (lambda message, level: None)
        self._warned: set[str] = set()

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self._log(message, "Warn")

    def read(self, frame: np.ndarray, box: Box) -> str | None:
        if self._current_screen() in PROTECTED_SCREENS:
            self._warn_once("captcha", "Number reader: not reading on the verification screen "
                                       "(that one is for you to answer).")
            return None
        try:
            return self.inner.read(frame, box)
        except Exception as exc:  # a failed read must never stop the macro
            self._warn_once(f"error:{type(exc).__name__}",
                            f"Number reader ({self.name}) failed: {exc}")
            return None


# name -> factory. Add other providers here later.
PROVIDERS: dict[str, Callable[[], NumberReader]] = {
    "built-in": BuiltinNumberReader,
}


def make_number_reader(current_screen: Callable[[], str], provider: str = "built-in",
                       log: LogFn | None = None) -> GuardedNumberReader:
    """Create the chosen reader, falling back to the built-in one if it's
    unknown, not installed, or fails to start."""
    log = log or (lambda message, level: None)
    factory = PROVIDERS.get(provider)
    if factory is None:
        log(f"Number reader '{provider}' isn't available; using the built-in reader.", "Warn")
        factory = PROVIDERS["built-in"]
    try:
        inner = factory()
    except Exception as exc:
        if factory is PROVIDERS["built-in"]:
            raise
        log(f"Number reader '{provider}' couldn't start ({exc}); using the built-in reader.", "Warn")
        inner = PROVIDERS["built-in"]()
    return GuardedNumberReader(inner, current_screen, log)
