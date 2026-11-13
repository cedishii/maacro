"""Background thread: read the latest Roblox frame a few times a second and work out the screen."""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from .capture import CaptureThread
from .game_state import GameTracker
from .vision.ocr import OcrReader
from .vision.screens import detect_screen


class DetectorThread(QThread):
    detection = Signal(object, float)   # Detection, milliseconds it took
    event = Signal(str, object)         # ("screen", "lobby"), ("result", "win"), ...
    failed = Signal(str)

    def __init__(self, capture: CaptureThread, interval_ms: int = 150, parent=None):
        super().__init__(parent)
        self.capture = capture
        self.interval_ms = interval_ms
        self.tracker = GameTracker()
        self.latest = None        # newest Detection (read by the macro thread)
        self.latest_count = 0     # goes up with every new Detection
        self.latest_time = 0.0    # when the frame behind `latest` was captured

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
            # On a slow PC a read can take most of a second: rest at least half
            # as long as it took, so screen reading never hogs a whole CPU core
            # (the game needs it more). Fast PCs keep the usual pace.
            took_ms = (time.perf_counter() - started) * 1000
            self.msleep(int(max(self.interval_ms, 0.5 * took_ms)))

    def _step(self, reader: OcrReader, last_id: int) -> int:
        """Read the newest frame if it's new. Returns its id."""
        frame_id, frame, frame_time = self.capture.latest_frame_info()
        if frame is None or frame_id == last_id:
            return last_id
        started = time.perf_counter()
        det = detect_screen(frame, reader.read(frame))
        self.latest = det
        self.latest_time = frame_time
        self.latest_count += 1
        self.detection.emit(det, (time.perf_counter() - started) * 1000)
        for kind, value in self.tracker.feed(det):
            self.event.emit(kind, value)
        return frame_id
