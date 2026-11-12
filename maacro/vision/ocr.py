"""Read text from a picture using the text recognition built into Windows."""
from __future__ import annotations

import asyncio
from typing import NamedTuple

import numpy as np
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter


class OcrWord(NamedTuple):
    text: str
    x: int
    y: int
    w: int
    h: int


class OcrLine(NamedTuple):
    """One line of text and where it is on the picture (in pixels)."""
    text: str
    x: int
    y: int
    w: int
    h: int
    words: tuple[OcrWord, ...] = ()

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2


class OcrReader:
    def __init__(self) -> None:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            raise RuntimeError(
                "Windows text recognition is not available. Install the English "
                "language pack in Windows Settings → Time & language → Language."
            )
        self._engine = engine

    def read(self, image: np.ndarray) -> list[OcrLine]:
        """Read every line of text in a BGR or BGRA picture."""
        if image.ndim == 3 and image.shape[2] == 3:
            alpha = np.full(image.shape[:2] + (1,), 255, dtype=np.uint8)
            image = np.concatenate([image, alpha], axis=2)
        image = np.ascontiguousarray(image, dtype=np.uint8)
        height, width = image.shape[:2]

        writer = DataWriter()
        writer.write_bytes(image.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, width, height)
        result = asyncio.run(self._recognize(bitmap))

        lines: list[OcrLine] = []
        for line in result.lines:
            rects = [word.bounding_rect for word in line.words]
            if not rects:
                continue
            left = min(r.x for r in rects)
            top = min(r.y for r in rects)
            right = max(r.x + r.width for r in rects)
            bottom = max(r.y + r.height for r in rects)
            words = tuple(OcrWord(w.text, int(r.x), int(r.y), int(r.width), int(r.height))
                          for w, r in zip(line.words, rects))
            lines.append(OcrLine(line.text, int(left), int(top),
                                 int(right - left), int(bottom - top), words))
        return lines

    async def _recognize(self, bitmap):
        return await self._engine.recognize_async(bitmap)
