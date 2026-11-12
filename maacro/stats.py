"""Session results: wins, losses, win rate and how long the macro has run."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal


class SessionStats(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wins = 0
        self.losses = 0
        self.pearls = 0             # SummerPearls earned this session
        self._elapsed_before = 0.0   # seconds from earlier start/stop periods
        self._started_at: float | None = None

    # --- results -------------------------------------------------------
    @property
    def runs(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        return (self.wins / self.runs * 100) if self.runs else 0.0

    def add_win(self) -> None:
        self.wins += 1
        self.changed.emit()

    def add_loss(self) -> None:
        self.losses += 1
        self.changed.emit()

    def add_pearls(self, amount: int) -> None:
        self.pearls += amount
        self.changed.emit()

    # --- session time --------------------------------------------------
    @property
    def running(self) -> bool:
        return self._started_at is not None

    def start(self) -> None:
        if not self.running:
            self._started_at = time.monotonic()
            self.changed.emit()

    def stop(self) -> None:
        if self.running:
            self._elapsed_before += time.monotonic() - self._started_at
            self._started_at = None
            self.changed.emit()

    @property
    def session_seconds(self) -> int:
        total = self._elapsed_before
        if self._started_at is not None:
            total += time.monotonic() - self._started_at
        return int(total)

    def session_time_text(self) -> str:
        s = self.session_seconds
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

    def reset(self) -> None:
        self.wins = self.losses = 0
        self.pearls = 0
        self._elapsed_before = 0.0
        if self._started_at is not None:
            self._started_at = time.monotonic()
        self.changed.emit()
