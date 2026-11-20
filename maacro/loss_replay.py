"""Loss replays: a short video of the minutes before each defeat.

While a match is on, a small picture of the game is kept every EVERY s (the
last SECONDS of them, as JPEG in memory: about 3 MB). When a run is lost they
are written to runs/<time>_loss.mp4, played fast (FPS pictures a second, so
3 minutes take ~22 s), so you can see where the defence broke instead of
guessing from the end screen. The newest KEEP videos are kept.
"""
from __future__ import annotations

import collections
import time
from pathlib import Path

import cv2
import numpy as np

from .runs import RUNS_DIR

EVERY = 2.0             # s between pictures
SECONDS = 180           # s of match kept
WIDTH = 640             # px wide (height follows the window)
FPS = 8                 # pictures a second in the video
KEEP = 10               # loss videos kept
RECORD_SCREENS = ("in_match", "card_pick", "unit_manager", "end")


class LossReplay:
    def __init__(self, seconds: float = SECONDS, every: float = EVERY, clock=time.monotonic):
        self.every = every
        self._clock = clock
        self._frames: collections.deque = collections.deque(maxlen=max(2, int(seconds / every)))
        self._last = -1e9

    def __len__(self) -> int:
        return len(self._frames)

    def clear(self) -> None:
        self._frames.clear()

    def detach(self) -> "LossReplay":
        """The kept pictures as a replay of their own (to save in the
        background); this one starts empty."""
        other = LossReplay(every=self.every, clock=self._clock)
        other._frames = self._frames
        self._frames = collections.deque(maxlen=other._frames.maxlen)
        return other

    def add(self, frame: np.ndarray | None, screen: str | None) -> bool:
        """Keep the picture if a match is on and EVERY s have passed."""
        now = self._clock()
        if frame is None or screen not in RECORD_SCREENS or now - self._last < self.every:
            return False
        image = frame[..., :3]
        height, width = image.shape[:2]
        if width > WIDTH:
            image = cv2.resize(image, (WIDTH, max(2, round(height * WIDTH / width) // 2 * 2)),
                               interpolation=cv2.INTER_AREA)
        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return False
        self._frames.append(data)
        self._last = now
        return True

    def save(self, folder: Path = RUNS_DIR, name: str | None = None, keep: int = KEEP) -> Path | None:
        """Write the kept pictures as an .mp4 (None if there are too few or it fails)."""
        if len(self._frames) < 3:
            return None
        images = [cv2.imdecode(d, cv2.IMREAD_COLOR) for d in self._frames]
        height, width = images[-1].shape[:2]
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        path = folder / (name or f"{time.strftime('%Y%m%d_%H%M%S')}_loss.mp4")
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
        if not writer.isOpened():
            return None
        try:
            for image in images:
                if image.shape[:2] != (height, width):
                    image = cv2.resize(image, (width, height))
                writer.write(image)
            # Hold the last picture for a second.
            for _ in range(FPS):
                writer.write(images[-1])
        finally:
            writer.release()
        for old in sorted(folder.glob("*_loss.mp4"))[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
        return path if path.exists() and path.stat().st_size > 0 else None


def latest_replay(folder: Path = RUNS_DIR) -> Path | None:
    videos = sorted(folder.glob("*_loss.mp4"))
    return videos[-1] if videos else None
