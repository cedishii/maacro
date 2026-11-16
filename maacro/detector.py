"""Background thread: read the latest Roblox frame a few times a second and work out the screen."""
from __future__ import annotations

import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from .capture import CaptureThread
from .game_state import GameTracker
from .vision.ocr import OcrReader
from .vision.screens import detect_screen
from .vision import fast_text  # noqa: F401  (the fast fuzzy_in, same answers; see fast_text.py)


THUMB = (96, 54)        # tiny copy of each frame, to tell if anything changed
SAME_PICTURE = 1.5      # largest difference (0–255) of any of the 9×12 regions for "the same picture"
# (measured: pixel noise 0.5; the smallest real changes — a hotbar counter, the
# "Not enough money!" text — 2.6 and 4.2)
REUSE_FOR = 1.0         # s: an unchanged picture reuses the last read this long at most
RELAXED_MS = 600        # between reads while the macro only watches (all placed and maxed)


def thumbnail(frame: np.ndarray) -> np.ndarray:
    # Every 4th pixel first: shrinking the full picture cost ~15 ms, this ~1 ms.
    return cv2.resize(np.ascontiguousarray(frame[::4, ::4, :3]), THUMB, interpolation=cv2.INTER_AREA).astype(np.int16)


def picture_change(a: np.ndarray, b: np.ndarray) -> float:
    """How much two thumbnails differ: the most-changed of 9×12 regions, so a
    small banner counts even when the rest of the picture is the same."""
    diff = np.abs(a - b).mean(axis=2)                       # 54 × 96
    return float(diff.reshape(9, 6, 12, 8).mean(axis=(1, 3)).max())


class DetectorThread(QThread):
    detection = Signal(object, float)   # Detection, milliseconds it took
    event = Signal(str, object)         # ("screen", "lobby"), ("result", "win"), ...
    failed = Signal(str)

    def __init__(self, capture: CaptureThread, interval_ms: int = 250, parent=None):
        super().__init__(parent)
        self.capture = capture
        self.interval_ms = interval_ms
        self.tracker = GameTracker()
        self.latest = None        # newest Detection (read by the macro thread)
        self.latest_count = 0     # goes up with every new Detection
        self.latest_time = 0.0    # when the frame behind `latest` was captured
        self.idle = False         # macro stopped and no page needs it: read once a second
        self.relaxed = False      # the macro is only watching: read a bit less often
        self.reads = self.reused = 0  # text recognition runs / unchanged pictures skipped
        self._thumb = None
        self._read_at = 0.0

    def run(self) -> None:
        try:
            reader = OcrReader()
        except Exception as exc:  # no OCR language installed, etc.
            self.failed.emit(str(exc))
            return
        last_id = -1
        while not self.isInterruptionRequested():
            started = time.perf_counter()
            try:
                last_id = self._step(reader, last_id)
            except Exception as exc:
                # Never let one bad frame end the thread: report and carry on.
                self.failed.emit(f"Screen reading error: {exc}")
                self.msleep(1000)
                continue
            # Rest at least as long as the read took: screen reading never
            # uses more than half a CPU core (the game needs it more).
            took_ms = (time.perf_counter() - started) * 1000
            rest = 1000 if self.idle else RELAXED_MS if self.relaxed else self.interval_ms
            self.msleep(int(max(rest, took_ms)))

    def _step(self, reader: OcrReader, last_id: int) -> int:
        """Read the newest frame if it's new. Returns its id."""
        frame_id, frame, frame_time = self.capture.latest_frame_info()
        if frame is None or frame_id == last_id:
            return last_id
        started = time.perf_counter()
        thumb = thumbnail(frame)
        same = (self.latest is not None and self._thumb is not None and thumb.shape == self._thumb.shape
                and time.monotonic() - self._read_at < REUSE_FOR
                and picture_change(thumb, self._thumb) < SAME_PICTURE)
        if same:
            # Practically the same picture as the last read: same answer,
            # without running the text recognition again.
            det = self.latest
            self.reused += 1
        else:
            det = detect_screen(frame, reader.read(frame))
            self._thumb, self._read_at = thumb, time.monotonic()
            self.reads += 1
        self.latest = det
        self.latest_time = frame_time
        self.latest_count += 1
        self.detection.emit(det, (time.perf_counter() - started) * 1000)
        for kind, value in self.tracker.feed(det):
            self.event.emit(kind, value)
        return frame_id
